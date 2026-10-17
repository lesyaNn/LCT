'use client';

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import Image from 'next/image';
import { useAuth } from '@/shared/auth/AuthProvider';
import { apiFetch } from '@/shared/lib/api-client';
import { formatFileSize } from '@/shared/lib/formatters';
import { getWorkflowAttachmentCategory } from '@/shared/lib/workflow-attachments';
import styles from './file-preview.module.css';

type Preview = {
  kind: 'image' | 'document' | 'table' | 'archive' | 'unsupported' | 'error';
  message?: string; src?: string; width?: number; height?: number;
  blocks?: { text: string; style: string }[];
  rows?: string[][]; sheet?: string;
  entries?: { name: string; size: number | null; directory: boolean; extension: string }[];
  total?: number; offset?: number;
};

// Only one floating preview owns the screen, including its in-flight request.
let activePreview: { id: string; close: () => void } | undefined;
type Phase = 'closed' | 'opening' | 'open' | 'closing';
const MOTION_MS = 160;

type FilePreviewProps = { children: ReactNode; path: string; name: string; size?: number | string; version?: string };

export function FilePreview(props: FilePreviewProps) {
  const { user, isAuthenticated } = useAuth();
  if (!user || !isAuthenticated) return <>{props.children}</>;
  return <FilePreviewContent key={`${user.id}:${props.path}:${props.version ?? ''}`} {...props} />;
}

function FilePreviewContent({ children, path, name, size, version = '' }: FilePreviewProps) {
  const { user } = useAuth();
  const id = useId();
  const host = useRef<HTMLSpanElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const openTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const finishTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const frames = useRef<number[]>([]);
  const phaseRef = useRef<Phase>('closed');
  const controller = useRef<AbortController | null>(null);
  const [phase, setPhase] = useState<Phase>('closed');
  const visible = phase !== 'closed';
  const [position, setPosition] = useState<CSSProperties>({ left: 12, top: 12 });
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const [imageReady, setImageReady] = useState(false);
  const [retry, setRetry] = useState(0);
  const category = getWorkflowAttachmentCategory(undefined, name);

  const changePhase = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);
  const cancelFrames = useCallback(() => {
    frames.current.forEach(cancelAnimationFrame);
    frames.current = [];
  }, []);
  const close = useCallback(() => {
    clearTimeout(openTimer.current);
    clearTimeout(leaveTimer.current);
    if (phaseRef.current === 'closed' || phaseRef.current === 'closing') return;
    cancelFrames();
    changePhase('closing');
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 30 : MOTION_MS;
    finishTimer.current = setTimeout(() => {
      changePhase('closed');
      if (activePreview?.id === id) activePreview = undefined;
    }, duration);
  }, [cancelFrames, changePhase, id]);

  const keep = () => {
    clearTimeout(leaveTimer.current);
    clearTimeout(finishTimer.current);
    if (phaseRef.current === 'closing') {
      if (activePreview?.id !== id) activePreview?.close();
      activePreview = { id, close };
      changePhase('open');
    }
  };
  const open = () => {
    keep();
    if (phaseRef.current !== 'closed') return;
    clearTimeout(openTimer.current);
    openTimer.current = setTimeout(() => {
      if (activePreview?.id !== id) activePreview?.close();
      activePreview = { id, close };
      setPage(0); setData(null); setError(''); setImageReady(false);
      changePhase('opening');
      // Position the panel before fading it in, with the skeleton already mounted.
      frames.current = [requestAnimationFrame(() => {
        frames.current.push(requestAnimationFrame(() => {
          if (phaseRef.current === 'opening') changePhase('open');
        }));
      })];
    }, 180);
  };
  const leave = (relatedTarget?: EventTarget | null) => {
    if (relatedTarget instanceof Node && (host.current?.contains(relatedTarget) || panel.current?.contains(relatedTarget))) return;
    clearTimeout(openTimer.current);
    clearTimeout(leaveTimer.current);
    leaveTimer.current = setTimeout(close, 300);
  };

  const updatePosition = useCallback(() => {
    const rect = host.current?.getBoundingClientRect();
    if (!rect) return;
    const desiredWidth = category === 'spreadsheet' ? 500 : 420;
    const width = Math.min(desiredWidth, window.innerWidth - 24);
    const imageHeight = data?.width && data?.height ? (width - 26) * data.height / data.width + 110 : null;
    const desiredHeight = imageHeight ?? (category === 'pdf' ? 560 : category === 'image' ? 360 : 430);
    const height = Math.min(Math.max(260, desiredHeight), 580, window.innerHeight - 24);
    const gap = 10;
    const rightFits = rect.right + gap + width <= window.innerWidth - 12;
    const leftFits = rect.left - gap - width >= 12;
    let left: number, top: number;
    if (rightFits || leftFits) {
      left = rightFits ? rect.right + gap : rect.left - gap - width;
      top = Math.max(12, Math.min(rect.top - 36, window.innerHeight - height - 12));
    } else {
      left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
      top = rect.bottom + gap + height <= window.innerHeight - 12 ? rect.bottom + gap : Math.max(12, rect.top - height - gap);
    }
    setPosition({ left, top, width, height });
  }, [category, data]);

  useLayoutEffect(() => { if (visible) updatePosition(); }, [visible, updatePosition]);
  useEffect(() => {
    if (!visible) return;
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
    const outside = (event: PointerEvent) => {
      if (!host.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) close();
    };
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    document.addEventListener('keydown', key);
    document.addEventListener('pointerdown', outside);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
      document.removeEventListener('keydown', key);
      document.removeEventListener('pointerdown', outside);
    };
  }, [visible, updatePosition, close]);

  useEffect(() => {
    if (!visible || !user) return;
    const request = new AbortController();
    controller.current = request;
    const timeout = setTimeout(() => { request.abort(); setError('Время ожидания истекло. Повторите попытку или скачайте файл.'); }, 15_000);
    void apiFetch<Preview>(`${path}?offset=${page * 100}`, { signal: request.signal }).then((result) => {
      if (request.signal.aborted) return;
      clearTimeout(timeout);
      if (result.ok) setData(result.data);
      else setError(result.status === 401 || result.status === 403 ? 'Нет доступа к файлу. Проверьте сеанс и права доступа.' : result.status === 404 ? 'Файл удалён или недоступен.' : 'Не удалось загрузить предпросмотр. Повторите попытку или скачайте файл.');
    });
    return () => { clearTimeout(timeout); request.abort(); };
  }, [visible, path, page, user, version, retry]);

  useEffect(() => () => {
    clearTimeout(openTimer.current); clearTimeout(leaveTimer.current); clearTimeout(finishTimer.current);
    cancelFrames(); controller.current?.abort();
    if (activePreview?.id === id) activePreview = undefined;
  }, [cancelFrames, id]);

  const loading = !error && (!data || (data.kind === 'image' && !imageReady));
  return <span className={styles.host} ref={host} onMouseEnter={(event) => { if (host.current?.contains(event.target as Node)) open(); }} onMouseLeave={(event) => leave(event.relatedTarget)}
    onFocusCapture={(event) => { if (host.current?.contains(event.target as Node)) open(); }} onBlurCapture={(event) => { if (!panel.current?.contains(event.relatedTarget as Node) && !host.current?.contains(event.relatedTarget as Node)) leave(event.relatedTarget); }}
    onClickCapture={(event) => { if (window.matchMedia('(hover: none)').matches && !visible) { event.preventDefault(); event.stopPropagation(); open(); } }}>
    {children}
    {visible && user ? createPortal(<div ref={panel} id={id} role="dialog" aria-label={`Предпросмотр: ${name}`} className={styles.panel} data-phase={phase} style={position} onMouseEnter={keep} onMouseLeave={(event) => leave(event.relatedTarget)} onFocusCapture={keep} onBlurCapture={(event) => { if (!panel.current?.contains(event.relatedTarget as Node) && !host.current?.contains(event.relatedTarget as Node)) leave(event.relatedTarget); }}>
      <header className={styles.header}><div><strong title={name}>{name}</strong><small>{name.split('.').pop()?.toUpperCase()} {typeof size === 'number' ? `· ${formatFileSize(size)}` : size ? `· ${size}` : ''}</small></div><button type="button" onClick={close} aria-label="Закрыть предпросмотр">×</button></header>
      <div className={styles.body} aria-busy={loading}>
        <div className={`${styles.skeleton} ${styles[category]} ${!loading ? styles.skeletonDone : ''}`} aria-hidden={!loading} role="status" aria-label="Загрузка предпросмотра">{Array.from({ length: category === 'image' ? 1 : 8 }, (_, index) => <span key={index} />)}</div>
        <div className={`${styles.result} ${loading ? styles.resultLoading : ''}`}>
        {error ? <div role="alert"><p>{error}</p><button type="button" onClick={() => { setData(null); setError(''); setImageReady(false); setRetry((value) => value + 1); }}>Повторить</button></div> : null}
        {data?.kind === 'image' && !error ? <ZoomableImage src={data.src!} name={name} width={data.width!} height={data.height!} onLoad={() => setImageReady(true)} onError={() => setError('Не удалось отобразить страницу или изображение. Файл можно скачать.')} /> : null}
        {data?.kind === 'document' ? <article className={styles.content}>{data.blocks?.map((block, index) => block.style === 'heading' ? <h3 key={index}>{block.text}</h3> : <p key={index}>{block.style === 'list' ? '• ' : ''}{block.text}</p>)}</article> : null}
        {data?.kind === 'table' ? <><p>{data.sheet}</p><div className={styles.tableScroll}><table><thead><tr><th scope="col">№</th>{data.rows?.[0]?.map((_, index) => <th key={index} scope="col">{String.fromCharCode(65 + index)}</th>)}</tr></thead><tbody>{data.rows?.map((row, index) => <tr key={index}><th scope="row">{index + 1}</th>{row.map((cell, column) => <td key={column}>{cell}</td>)}</tr>)}</tbody></table></div></> : null}
        {data?.kind === 'archive' ? <><ul className={styles.entries}>{data.entries?.map((entry, index) => <li key={index} title={entry.name}><span>{entry.directory ? '📁 ' : ''}{entry.name}</span><small>{entry.directory ? 'Папка' : entry.extension.toUpperCase()} {entry.size !== null ? formatFileSize(entry.size) : ''}</small></li>)}</ul><nav className={styles.pagination} aria-label="Содержимое архива"><button type="button" disabled={page === 0} onClick={() => { setData(null); setImageReady(false); setPage((value) => value - 1); }}>Назад</button><span>{(data.offset ?? 0) + (data.entries?.length ? 1 : 0)}–{(data.offset ?? 0) + (data.entries?.length ?? 0)} из {data.total}</span><button type="button" disabled={(page + 1) * 100 >= (data.total ?? 0)} onClick={() => { setData(null); setImageReady(false); setPage((value) => value + 1); }}>Далее</button></nav></> : null}
        {data?.message ? <p role={data.kind === 'error' ? 'alert' : 'status'}>{data.message}</p> : null}
        </div>
      </div>
      <footer className={styles.footer}>{data?.kind === 'image' && imageReady ? <span>Колесо — масштаб · перетаскивание — перемещение.</span> : null}<span>Для скачивания нажмите на имя файла.</span></footer>
    </div>, document.body) : null}
  </span>;
}


function ZoomableImage({ src, name, width, height, onLoad, onError }: {
  src: string; name: string; width: number; height: number;
  onLoad: () => void; onError: () => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const scale = useRef(1);
  const anchor = useRef<{ left: number; top: number } | null>(null);
  const drag = useRef<{ id: number; x: number; y: number; left: number; top: number } | null>(null);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      if (!event.deltaY) return;
      event.preventDefault();
      event.stopPropagation();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1);
      const next = Math.max(1, Math.min(5, scale.current * Math.exp(-Math.max(-200, Math.min(200, delta)) * 0.002)));
      if (next === scale.current) return;
      const rect = element.getBoundingClientRect();
      const x = event.clientX - rect.left - element.clientLeft;
      const y = event.clientY - rect.top - element.clientTop;
      const ratio = next / scale.current;
      anchor.current = { left: (element.scrollLeft + x) * ratio - x, top: (element.scrollTop + y) * ratio - y };
      scale.current = next;
      setZoom(next);
    };
    // React wheel handlers are passive; zoom must consume wheel only inside this viewport.
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, []);

  useLayoutEffect(() => {
    if (!viewport.current || !anchor.current) return;
    viewport.current.scrollLeft = anchor.current.left;
    viewport.current.scrollTop = anchor.current.top;
    anchor.current = null;
  }, [zoom]);

  return <div ref={viewport} className={styles.zoomViewport} tabIndex={0}
    role="region" aria-label={`${name}: масштаб ${Math.round(zoom * 100)}%. Колесо мыши — масштаб, перетаскивание — перемещение.`}
    onPointerDown={(event) => {
      if (event.button !== 0 || scale.current === 1) return;
      drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, left: event.currentTarget.scrollLeft, top: event.currentTarget.scrollTop };
      event.currentTarget.setPointerCapture(event.pointerId);
      event.preventDefault();
    }}
    onPointerMove={(event) => {
      if (!drag.current || drag.current.id !== event.pointerId) return;
      event.currentTarget.scrollLeft = drag.current.left - (event.clientX - drag.current.x);
      event.currentTarget.scrollTop = drag.current.top - (event.clientY - drag.current.y);
    }}
    onPointerUp={(event) => { drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
    onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }}
    onKeyDown={(event) => {
      if (!['+', '=', '-', '0'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === '0' ? 1 : Math.max(1, Math.min(5, scale.current * (event.key === '-' ? 1 / 1.2 : 1.2)));
      scale.current = next; setZoom(next);
    }}>
    <div className={styles.zoomCanvas} style={{ width: `${zoom * 100}%`, height: `${zoom * 100}%`, cursor: zoom > 1 ? 'grab' : 'zoom-in' }}>
      <Image className={styles.image} src={src} alt={name} width={width} height={height} unoptimized draggable={false} onLoad={onLoad} onError={onError} />
    </div>
  </div>;
}
