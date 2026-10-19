'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Editor } from '@tiptap/core';
import { useAuth } from '@/shared/auth/AuthProvider';
import { noteApi, type NoteSummary } from '@/shared/lib/notes-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { Icon } from '@/shared/ui/rtk/icon';
import { Modal } from '@/shared/ui/rtk/modal';
import { NoteEditor } from './note-editor';
import { NoteExport } from './note-export';
import { useNotesStore } from './use-notes-store';
import styles from './notes.module.css';

const date = (value: string) => new Date(value).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

export function NotesPage({ requestedId }: { requestedId?: string }) {
  const { user } = useAuth();
  return user ? <PersonalNotes key={user.id} owner={user.id} requestedId={requestedId} /> : null;
}

function PersonalNotes({ owner, requestedId }: { owner: string; requestedId?: string }) {
  const router = useRouter();
  const store = useNotesStore(owner);
  const [selected, setSelected] = useState<string | null>(requestedId ?? null);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('updated_at:desc');
  const [rows, setRows] = useState<NoteSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [listError, setListError] = useState('');
  const [openError, setOpenError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(null);
  const activeRequest = useRef(0);
  const welcomeReady = useRef(false);
  const pageRoot = useRef<HTMLElement>(null);
  const entry = selected ? store.entries.get(selected) : undefined;
  const note = entry?.note;
  const savedSignature = [...store.entries.values()].map((entry) => `${entry.note.id}:${entry.note.revision}:${entry.creating}`).join('|');

  useLayoutEffect(() => { pageRoot.current?.scrollIntoView({ block: 'start' }); }, [selected]);

  const loadNote = useCallback(async (id: string) => {
    const request = ++activeRequest.current;
    setOpenError(''); setOpening(true);
    try { await store.open(id); }
    catch (error) { if (request === activeRequest.current) setOpenError((error as Error).message); }
    finally { if (request === activeRequest.current) setOpening(false); }
  }, [store]);

  const choose = (id: string) => {
    setSelected(id); setOpenError('');
    router.push(`/notes?note=${encodeURIComponent(id)}`, { scroll: false });
  };
  const backToList = () => {
    activeRequest.current++;
    setSelected(null); setOpening(false); setOpenError('');
    router.push('/notes', { scroll: false });
  };

  useEffect(() => {
    const timer = setTimeout(() => setSelected(requestedId ?? null), 0);
    return () => clearTimeout(timer);
  }, [requestedId]);

  useEffect(() => {
    const timer = setTimeout(() => { if (selected) void loadNote(selected); }, 0);
    return () => clearTimeout(timer);
  }, [selected, loadNote]);

  useEffect(() => {
    const abort = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true); setListError('');
      if (!welcomeReady.current) {
        const initialized = await noteApi.initialize();
        if (abort.signal.aborted) return;
        if (!initialized.ok) { setListError('Не удалось подготовить заметки.'); setLoading(false); return; }
        welcomeReady.current = true;
      }
      const [sort_by, sort_order] = sort.split(':');
      // The server caps a page at 100; fetch additional pages without losing
      // the current selection or editor state.
      const items: NoteSummary[] = [];
      let foundTotal = 0;
      for (let offset = 0; offset < limit; offset += 100) {
        const result = await noteApi.list(new URLSearchParams({ q: query.trim(), sort_by, sort_order, offset: String(offset), limit: String(Math.min(100, limit - offset)) }), abort.signal);
        if (abort.signal.aborted) return;
        if (!result.ok) { setListError('Не удалось загрузить заметки.'); setLoading(false); return; }
        items.push(...result.data.items); foundTotal = result.data.total;
        if (items.length >= foundTotal) break;
      }
      setRows(items); setTotal(foundTotal); setLoading(false);
    }, 250);
    return () => { abort.abort(); clearTimeout(timer); };
  }, [query, sort, limit, refresh, savedSignature]);

  const create = () => {
    const id = store.create(); setQuery(''); choose(id);
  };
  // Merge local edits/unsaved creations into the compact list, including offline.
  const merged = new Map(rows.map((row) => [row.id, row]));
  for (const [id, draft] of store.entries) {
    if (!draft.dirty && !merged.has(id)) continue;
    const current = draft.note;
    const matches = `${current.title}\n${current.content}`.toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru'));
    if (matches) merged.set(id, { ...current, snippet: current.content.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/[#*`>~]/g, '').replace(/\s+/g, ' ').slice(0, 130) });
    else merged.delete(id);
  }
  const [sortField, sortDirection] = sort.split(':') as ['created_at' | 'updated_at', string];
  const visible = [...merged.values()].sort((a, b) => (a[sortField].localeCompare(b[sortField]) * (sortDirection === 'asc' ? 1 : -1)) || a.id.localeCompare(b.id));

  return <section ref={pageRoot} className={styles.page} aria-label="Личные заметки">
    <header className={styles.pageHeader}>{selected ? <Button variant="ghost" size="m" onClick={backToList}>← Все заметки</Button> : <div><h1>Заметки</h1><p>Личные записи, идеи и рабочие планы</p></div>}<Button variant="primary" size="m" onClick={create}>+ Новая заметка</Button></header>
    <div className={styles.workspace}>
      {!selected ? <section className={styles.list} aria-label="Список заметок">
        <div className={styles.filters}>
          <Input type="search" aria-label="Поиск заметок" placeholder="Поиск по заметкам…" maxLength={100} value={query} onChange={(event) => { setQuery(event.target.value); setLimit(50); }} />
          <Select aria-label="Сортировка заметок" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="updated_at:desc">Сначала изменённые недавно</option><option value="updated_at:asc">Сначала давно изменённые</option><option value="created_at:desc">Сначала новые</option><option value="created_at:asc">Сначала старые</option>
          </Select>
        </div>
        {listError ? <div className={styles.notice} role="alert">{listError} <button type="button" onClick={() => setRefresh((value) => value + 1)}>Повторить</button></div> : null}
        {loading ? <p className={styles.listMessage} role="status">Загрузка заметок…</p> : null}
        {!loading && !visible.length && !listError ? <div className={styles.listEmpty}><Icon name="notes" size={28} /><strong>{query ? 'Ничего не найдено' : 'Здесь будут ваши заметки'}</strong><p>{query ? 'Попробуйте другой запрос' : 'Создайте первую запись — её увидите только вы'}</p>{!query ? <Button size="s" onClick={create}>Создать заметку</Button> : null}</div> : null}
        <div className={styles.noteList}>{visible.map((row) => <button type="button" key={row.id} className={`${styles.noteRow} ${row.id === selected ? styles.selected : ''}`} aria-current={row.id === selected ? 'true' : undefined} onClick={() => void choose(row.id)}>
          <strong>{row.title.trim() || 'Без названия'}</strong><span>{row.snippet || 'Пустая заметка'}</span><small>{date(row.updated_at)}{store.entries.get(row.id)?.dirty ? ' · Черновик' : ''}</small>
        </button>)}</div>
        {rows.length < total ? <Button variant="ghost" size="s" onClick={() => setLimit((value) => value + 100)}>Показать ещё</Button> : null}
      </section> : <article className={styles.document} aria-label="Редактор заметки">
        {opening && !note ? <p role="status" className={styles.empty}>Открываем заметку…</p> : openError && !note ? <div className={styles.empty} role="alert"><p>{openError}</p><Button size="s" onClick={() => selected && void loadNote(selected)}>Повторить</Button></div> : note ? <>
          <div className={styles.documentHeader}><span className={styles.saveStatus} role="status" aria-live="polite">{entry?.saving ? 'Сохранение…' : entry?.error ? 'Не сохранено' : entry?.dirty ? 'Ожидает сохранения…' : 'Сохранено'}</span><span className={styles.modified}>Изменено {date(note.updated_at)}</span><div className={styles.documentActions}><NoteExport key={note.id} editor={editor} title={note.title} markdown={note.content} /><Button variant="ghost" size="m" disabled={Boolean(entry?.saving || deleting)} onClick={() => setDeleteOpen(true)}>Удалить</Button></div></div>
          {store.storageError ? <div className={styles.notice} role="alert">Браузер не разрешает хранить черновик. Дождитесь статуса «Сохранено» перед закрытием страницы.</div> : null}
          {entry?.error ? <div className={styles.notice} role="alert"><p>{entry.error}</p>{entry.conflict || entry.missing ? <>
            <Button size="s" onClick={() => { choose(store.copy(note.id)); }}>Сохранить копию моего текста</Button>
            {entry.remote ? <details><summary>Версия на сервере</summary><strong>{entry.remote.title || 'Без названия'}</strong><pre className={styles.remoteContent}>{entry.remote.content}</pre></details> : null}
          </> : <Button size="s" onClick={() => void store.save(note.id)}>Повторить сохранение</Button>}</div> : null}
          <input className={styles.title} aria-label="Заголовок заметки" placeholder="Без названия" maxLength={300} value={note.title} onChange={(event) => store.edit(note.id, { title: event.target.value })} />
          <NoteEditor key={`${note.id}:${entry?.editorKey ?? 0}`} initialValue={note.content} onReady={setEditor} onChange={(content) => store.edit(note.id, { content })} />
        </> : <div className={styles.empty}><Icon name="notes" size={38} /><h2>Место для ваших мыслей</h2><p>Откройте заметку или начните с чистого листа</p><Button size="s" onClick={create}>Создать заметку</Button></div>}
      </article>}
    </div>
    {deleteOpen && note ? <Modal title="Удалить заметку?" onClose={() => { if (!deleting) setDeleteOpen(false); }}><p>«{note.title || 'Без названия'}» будет удалена. Восстановить её не получится.</p><div className={styles.dialogActions}><Button size="s" disabled={deleting} onClick={() => setDeleteOpen(false)}>Отмена</Button><Button variant="danger" size="s" disabled={deleting || entry?.saving} loading={deleting} onClick={async () => {
      setDeleting(true); const removed = await store.remove(note.id); setDeleting(false); setDeleteOpen(false);
      if (removed) {
        setRows((items) => items.filter((item) => item.id !== note.id)); setRefresh((value) => value + 1);
        backToList();
      }
    }}>Удалить</Button></div></Modal> : null}
  </section>;
}
