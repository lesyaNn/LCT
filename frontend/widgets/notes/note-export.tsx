'use client';

import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { Editor } from '@tiptap/core';
import { noteApi } from '@/shared/lib/notes-repository';
import { downloadBlob } from '@/shared/lib/download-blob';
import { Button } from '@/shared/ui/rtk/button';
import styles from './notes.module.css';

function filename(title: string) {
  return (title.trim() || 'Без названия').normalize('NFC')
    .replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, '-').replace(/[. ]+$/g, '').slice(0, 100) || 'Заметка';
}

export function NoteExport({ editor, title, markdown }: { editor: Editor | null; title: string; markdown: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const focusLast = useRef(false);
  const menuId = useId();
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => { request.current?.abort(); }, []);

  function close() {
    setOpen(false);
    root.current?.querySelector<HTMLButtonElement>('[aria-haspopup="menu"]')?.focus({ preventScroll: true });
  }

  useLayoutEffect(() => {
    if (!open) return;
    const items = menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]');
    items?.[focusLast.current ? items.length - 1 : 0]?.focus({ preventScroll: true });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);

  async function pdf() {
    if (!editor || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    const name = filename(title);
    setLoading(true); setError('');
    try {
      const result = await noteApi.exportPdf(title, editor.getJSON(), controller.signal);
      if (controller.signal.aborted) return;
      if (!result.ok || !result.data.type.includes('application/pdf')) throw new Error('Не удалось сформировать PDF. Повторите попытку.');
      downloadBlob(result.data, `${name}.pdf`);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Не удалось скачать PDF.');
    } finally {
      if (request.current === controller) request.current = null;
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return <div ref={root} className={styles.exportArea}>
    <Button size="m" variant="ghost" disabled={!editor || editor.isDestroyed || loading} loading={loading}
      aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
      onClick={() => { setError(''); focusLast.current = false; setOpen((value) => !value); }}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault(); setError(''); focusLast.current = event.key === 'ArrowUp'; setOpen(true);
        }
      }}>Экспорт <span aria-hidden="true">⌄</span></Button>
    {open ? <div ref={menu} id={menuId} className={styles.exportMenu} role="menu" aria-label="Формат экспорта"
      onKeyDown={(event) => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
        else if (event.key === 'Tab') close();
        else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? []);
          const current = items.indexOf(document.activeElement as HTMLButtonElement);
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
            : (current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
          items[next]?.focus({ preventScroll: true });
        }
      }}>
      <button type="button" role="menuitem" onClick={() => { close(); void pdf(); }}>PDF <small>.pdf</small></button>
      <button type="button" role="menuitem" onClick={() => {
        close();
        setError('');
        const heading = (title.trim() || 'Без названия').replace(/[\r\n]+/g, ' ').replace(/([\\`*_{}\[\]()#+.!<>~-])/g, '\\$1');
        downloadBlob(new Blob([`# ${heading}\n\n${markdown}\n`], { type: 'text/markdown;charset=utf-8' }), `${filename(title)}.md`);
      }}>Markdown <small>.md</small></button>
    </div> : null}
    {error ? <span className={styles.exportError} role="alert">{error}</span> : null}
  </div>;
}
