'use client';

import Link from 'next/link';
import { memo, useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import MapIcon from '@atomaro/icons/24/navigation/Map';
import BookOpen from '@atomaro/icons/24/culture/BookOpen';
import ZoomIn from '@atomaro/icons/24/media/ZoomIn';
import ZoomOut from '@atomaro/icons/24/media/ZoomOut';
import { Button } from '@/shared/ui/rtk/button';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { getUniversityMap, universitiesMapQueryKey, type UniversityFilters, type UniversityMapItem } from '@/shared/lib/universities-repository';
import styles from './universities-map.module.css';

type MapRegion = { code: string; name: string; path: string };
type MapGeometry = { viewBox: string; regions: MapRegion[] };
type RegionStats = { universities: UniversityMapItem[]; launched: number; activeWorkflow: number };
type Transform = { scale: number; x: number; y: number };

const WIDTH = 1160;
const HEIGHT = 450;
const EMPTY: RegionStats = { universities: [], launched: 0, activeWorkflow: 0 };

function countLabel(count: number, one: string, few: string, many: string): string {
  const form = new Intl.PluralRules('ru-RU').select(count);
  return `${count} ${form === 'one' ? one : form === 'few' ? few : many}`;
}

function level(count: number): number {
  if (!count) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  if (count <= 7) return 3;
  return 4;
}

function clampTransform(next: Transform): Transform {
  const scale = Math.min(5, Math.max(1, next.scale));
  return {
    scale,
    x: Math.max(-WIDTH * (scale - 1) - 70, Math.min(70, next.x)),
    y: Math.max(-HEIGHT * (scale - 1) - 45, Math.min(45, next.y)),
  };
}

function transformAttribute({ x, y, scale }: Transform): string {
  return `translate(${x} ${y}) scale(${scale})`;
}

const RegionPaths = memo(function RegionPaths({ regions, byRegion, selected }: {
  regions: MapRegion[];
  byRegion: Map<string, RegionStats>;
  selected: string | null;
}) {
  return regions.map((region) => {
    const stats = byRegion.get(region.code) ?? EMPTY;
    return <path key={region.code} data-region-code={region.code} data-level={level(stats.universities.length)} data-selected={selected === region.code || undefined} d={region.path} fillRule="evenodd" className={styles.region} role="button" tabIndex={0} aria-label={`${region.name}: ${stats.universities.length} вузов`} />;
  });
});

function RegionDetails({ title, stats, onClose, hideHeader = false }: { title: string; stats: RegionStats; onClose: () => void; hideHeader?: boolean }) {
  const [limit, setLimit] = useState(30);
  return <div className={styles.details}>
    {!hideHeader ? <div className={styles.detailsHeader}>
      <div><span className={styles.eyebrow}>Регион</span><h3>{title}</h3></div>
      <button type="button" className={styles.close} onClick={onClose} aria-label="Закрыть сведения о регионе">×</button>
    </div> : null}
    <div className={styles.detailsMetrics}>
      <span>{countLabel(stats.universities.length, 'вуз', 'вуза', 'вузов')}</span>
      <span>{countLabel(stats.launched, 'программа запущена', 'программы запущены', 'программ запущено')}</span>
      <span>{countLabel(stats.activeWorkflow, 'вуз с активным Workflow', 'вуза с активным Workflow', 'вузов с активным Workflow')}</span>
    </div>
    {stats.universities.length === 0 ? <p className={styles.emptyDetails}>По выбранным условиям вузов в этом регионе нет.</p> :
      <ul className={styles.universityList}>{stats.universities.slice(0, limit).map((item) => <li key={item.id}>
        <strong>{item.name}</strong>
        <span>{item.city}</span>
        <div className={styles.universityMeta}>
          <span>Связано программ: {item.programsCount}</span>
          {item.launchedPrograms > 0 ? <span>{countLabel(item.launchedPrograms, 'программа запущена', 'программы запущены', 'программ запущено')}</span> : null}
          {item.activePrograms > 0 ? <span>{countLabel(item.activePrograms, 'программа в работе', 'программы в работе', 'программ в работе')}</span> : null}
          {item.activeWorkflow ? <StatusBadge intent="brand">Активный Workflow</StatusBadge> : null}
        </div>
        <Link href={`/universities/${item.id}`}>Открыть паспорт <span aria-hidden="true">→</span></Link>
      </li>)}</ul>}
    {stats.universities.length > limit ? <Button variant="ghost" size="s" onClick={() => setLimit((current) => current + 30)}>Показать ещё</Button> : null}
  </div>;
}

export function UniversitiesMap({ filters, scopeKey }: { filters: UniversityFilters; scopeKey: string }) {
  const geometryQuery = useQuery({
    queryKey: ['russia-regions-geometry'],
    queryFn: async ({ signal }): Promise<MapGeometry> => {
      const response = await fetch('/maps/russia-regions.json', { signal });
      if (!response.ok) throw new Error('Не удалось загрузить границы регионов.');
      return response.json() as Promise<MapGeometry>;
    },
    staleTime: Infinity,
  });
  const dataQuery = useQuery({
    queryKey: [...universitiesMapQueryKey(filters), scopeKey],
    queryFn: ({ signal }) => getUniversityMap(filters, signal),
    enabled: Boolean(scopeKey),
    staleTime: 5 * 60_000,
  });
  const viewportRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const mapGroupRef = useRef<SVGGElement>(null);
  const frameRef = useRef<number | null>(null);
  const transformRef = useRef<Transform>({ scale: 1, x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number; pixelsPerUnit: number; code: string | null; moved: boolean } | null>(null);
  const hoverCodeRef = useRef<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hover, setHover] = useState<{ code: string; x: number; y: number } | null>(null);
  const [mobile, setMobile] = useState(false);

  const applyTransform = useCallback((next: Transform) => {
    transformRef.current = clampTransform(next);
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      mapGroupRef.current?.setAttribute('transform', transformAttribute(transformRef.current));
    });
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 768px)');
    const update = () => {
      setMobile(media.matches);
      applyTransform(media.matches ? { scale: 1.8, x: -50, y: -216 } : { scale: 1, x: 0, y: 0 });
    };
    update();
    media.addEventListener('change', update);
    return () => {
      media.removeEventListener('change', update);
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [applyTransform]);

  useEffect(() => {
    if (geometryQuery.data && dataQuery.data) applyTransform(transformRef.current);
  }, [applyTransform, geometryQuery.data, dataQuery.data]);

  const regions = geometryQuery.data?.regions;
  const regionNames = useMemo(() => new Map(regions?.map((item) => [item.code, item.name]) ?? []), [regions]);
  const { byRegion, unmapped, totalLaunched, totalActive } = useMemo(() => {
    const byRegion = new Map<string, RegionStats>();
    const unmapped: RegionStats = { universities: [], launched: 0, activeWorkflow: 0 };
    let totalLaunched = 0;
    let totalActive = 0;
    for (const item of dataQuery.data ?? []) {
      const target = item.regionCode && regionNames.has(item.regionCode)
        ? (byRegion.get(item.regionCode) ?? { universities: [], launched: 0, activeWorkflow: 0 })
        : unmapped;
      target.universities.push(item);
      target.launched += item.launchedPrograms;
      target.activeWorkflow += Number(item.activeWorkflow);
      totalLaunched += item.launchedPrograms;
      totalActive += Number(item.activeWorkflow);
      if (target !== unmapped && item.regionCode) byRegion.set(item.regionCode, target);
    }
    return { byRegion, unmapped, totalLaunched, totalActive };
  }, [dataQuery.data, regionNames]);

  const selectedStats = selected === 'unmapped' ? unmapped : byRegion.get(selected ?? '') ?? EMPTY;
  const selectedTitle = selected === 'unmapped' ? 'Вузы — без определённого региона' : `Вузы — ${regionNames.get(selected ?? '') ?? ''}`;
  const hoveredStats = byRegion.get(hover?.code ?? '') ?? EMPTY;

  const svgPoint = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    return matrix ? new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse()) : { x: WIDTH / 2, y: HEIGHT / 2 };
  };
  const zoom = (factor: number, x = WIDTH / 2, y = HEIGHT / 2) => {
    const current = transformRef.current;
    const scale = Math.min(5, Math.max(1, current.scale * factor));
    const ratio = scale / current.scale;
    applyTransform({ scale, x: x - (x - current.x) * ratio, y: y - (y - current.y) * ratio });
  };
  const onWheel = (event: WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const point = svgPoint(event.clientX, event.clientY);
    zoom(event.deltaY < 0 ? 1.2 : 1 / 1.2, point.x, point.y);
  };
  const onPointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    const target = event.target as Element;
    dragRef.current = { x: event.clientX, y: event.clientY, pixelsPerUnit: svgRef.current?.getScreenCTM()?.a || 1, code: target.closest('[data-region-code]')?.getAttribute('data-region-code') ?? null, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.dataset.dragging = 'true';
    hoverCodeRef.current = null;
    setHover(null);
  };
  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag) {
      if (event.pointerType === 'mouse') {
        const code = (event.target as Element).closest('[data-region-code]')?.getAttribute('data-region-code') ?? null;
        if (code !== hoverCodeRef.current) {
          if (code) showHover(code, event.clientX, event.clientY);
          else clearHover();
        }
      }
      return;
    }
    const deltaX = event.clientX - drag.x;
    const deltaY = event.clientY - drag.y;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 3) drag.moved = true;
    if (drag.moved) {
      const current = transformRef.current;
      applyTransform({ ...current, x: current.x + deltaX / drag.pixelsPerUnit, y: current.y + deltaY / drag.pixelsPerUnit });
      drag.x = event.clientX;
      drag.y = event.clientY;
    }
  };
  const onPointerUp = (event: PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    delete event.currentTarget.dataset.dragging;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (drag && !drag.moved && drag.code) setSelected(drag.code);
  };
  const showHover = (code: string, clientX: number, clientY: number) => {
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) return;
    hoverCodeRef.current = code;
    setHover({ code, x: Math.min(rect.width - 160, Math.max(150, clientX - rect.left)), y: Math.min(rect.height - 104, Math.max(8, clientY - rect.top + 12)) });
  };
  const clearHover = () => {
    if (hoverCodeRef.current === null) return;
    hoverCodeRef.current = null;
    setHover(null);
  };
  const selectFromPicker = (code: string) => {
    if (!code) return;
    setSelected(code);
    const path = Array.from(svgRef.current?.querySelectorAll<SVGPathElement>('[data-region-code]') ?? [])
      .find((item) => item.getAttribute('data-region-code') === code);
    if (!path) return;
    const box = path.getBBox();
    const scale = Math.max(transformRef.current.scale, 2);
    applyTransform({ scale, x: WIDTH / 2 - (box.x + box.width / 2) * scale, y: HEIGHT / 2 - (box.y + box.height / 2) * scale });
  };

  if (geometryQuery.isPending || dataQuery.isPending) return <div className={styles.loading} role="status">Загружаем карту вузов…</div>;
  if (geometryQuery.isError || dataQuery.isError) return <RouteErrorState onRetry={() => { void geometryQuery.refetch(); void dataQuery.refetch(); }} />;

  return <section className={styles.mapSection} aria-label="География вузов по регионам">
    <div className={styles.kpis}>
      <div><MapIcon size={20} fill="currentColor" /><span>Регионов с вузами</span><strong>{byRegion.size}</strong></div>
      <div><BookOpen size={20} fill="currentColor" /><span>Вузов</span><strong>{dataQuery.data.length}</strong></div>
      <div><BookOpen size={20} fill="currentColor" /><span>Программ запущено</span><strong>{totalLaunched}</strong></div>
      <div><MapIcon size={20} fill="currentColor" /><span>Вузов с активным Workflow</span><strong>{totalActive}</strong></div>
    </div>
    {dataQuery.isFetching ? <p className={styles.updating} role="status">Обновляем данные карты…</p> : null}
    <div className={styles.layout}>
      <div className={styles.mapCard}>
        <div className={styles.cardTop}>
          <div><h2>География взаимодействий</h2><p>Выберите регион, чтобы увидеть его вузы</p></div>
          <div className={styles.cardActions}>
          <select className={styles.regionPicker} aria-label="Перейти к региону" value={selected && selected !== 'unmapped' ? selected : ''} onChange={(event) => selectFromPicker(event.target.value)}>
            <option value="">Найти регион</option>
            {regions?.map((region) => <option value={region.code} key={region.code}>{region.name}</option>)}
          </select>
          <div className={styles.controls} aria-label="Масштаб карты">
            <Button size="s" variant="ghost" onClick={() => zoom(1.3)} aria-label="Увеличить карту"><ZoomIn size={18} fill="currentColor" /></Button>
            <Button size="s" variant="ghost" onClick={() => zoom(1 / 1.3)} aria-label="Уменьшить карту"><ZoomOut size={18} fill="currentColor" /></Button>
            <Button size="s" variant="ghost" onClick={() => applyTransform({ scale: 1, x: 0, y: 0 })}>Сбросить</Button>
          </div>
          </div>
        </div>
        <div className={styles.viewport} ref={viewportRef}>
          <svg ref={svgRef} className={styles.svg} viewBox={geometryQuery.data.viewBox} role="img" aria-label="Интерактивная карта регионов и территорий" onWheel={onWheel} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={(event) => { dragRef.current = null; delete event.currentTarget.dataset.dragging; }} onPointerLeave={clearHover} onKeyDown={(event) => { if (event.key !== 'Enter' && event.key !== ' ') return; const code = (event.target as Element).closest('[data-region-code]')?.getAttribute('data-region-code'); if (code) { event.preventDefault(); setSelected(code); } }} onFocus={(event) => { const target = (event.target as Element).closest('[data-region-code]'); const code = target?.getAttribute('data-region-code'); if (target && code) { const rect = target.getBoundingClientRect(); showHover(code, rect.left + rect.width / 2, rect.top); } }} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) clearHover(); }}>
            <g ref={mapGroupRef} transform="translate(0 0) scale(1)">
              <RegionPaths regions={regions ?? []} byRegion={byRegion} selected={selected} />
            </g>
          </svg>
          {hover ? <div className={styles.tooltip} role="tooltip" style={{ left: hover.x, top: hover.y }}><strong>{regionNames.get(hover.code)}</strong>{hoveredStats.universities.length ? <><span>Вузов: {hoveredStats.universities.length}</span><span>Программ запущено: {hoveredStats.launched}</span><span>Вузов с активным Workflow: {hoveredStats.activeWorkflow}</span></> : <span>Нет вузов по выбранным условиям</span>}</div> : null}
        </div>
        <div className={styles.cardBottom}>
          <div className={styles.legend}><span>Вузов в регионе</span>{[['0', 'Нет'], ['1', '1'], ['2', '2–3'], ['3', '4–7'], ['4', '8+']].map(([tone, label]) => <span key={tone}><i data-level={tone} />{label}</span>)}</div>
          <span className={styles.hint}>Колесо мыши — масштаб · Перетаскивание — перемещение</span>
          <span className={styles.mobileHint}>Перетаскивайте карту · Кнопки +/− меняют масштаб</span>
        </div>
        {unmapped.universities.length > 0 ? <button type="button" className={styles.unmapped} onClick={() => setSelected('unmapped')}>Без определённого региона: {unmapped.universities.length} вузов · Показать</button> : null}
        {dataQuery.data.length === 0 ? <p className={styles.noResults}>По выбранным условиям вузов не найдено. Измените фильтры, чтобы увидеть их на карте.</p> : null}
        <details className={styles.attribution}>
          <summary>Источники карты</summary>
          <p>Границы: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a> · Города: <a href="https://www.geonames.org/about.html" target="_blank" rel="noreferrer">GeoNames</a> (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>). Данные городов обработаны для привязки к регионам. Статус и границы ряда территорий оспариваются.</p>
        </details>
      </div>
      {selected && !mobile ? <aside className={styles.sidePanel}><RegionDetails key={`${selected}-${JSON.stringify(filters)}`} title={selectedTitle} stats={selectedStats} onClose={() => setSelected(null)} /></aside> : null}
    </div>
    {selected && mobile ? <Drawer title={selectedTitle} onClose={() => setSelected(null)}><RegionDetails key={`${selected}-${JSON.stringify(filters)}`} title={selectedTitle} stats={selectedStats} onClose={() => setSelected(null)} hideHeader /></Drawer> : null}
  </section>;
}
