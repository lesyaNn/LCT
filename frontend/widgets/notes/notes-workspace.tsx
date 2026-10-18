'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { notesApi, type NoteSort, type NoteView } from '@/shared/lib/notes-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { Button } from '@/shared/ui/rtk/button';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { NotesEditor } from './notes-editor';
import type { NoteInsertion } from './notes-launcher';
import styles from './notes.module.css';

const views: { id: NoteView; label: string }[] = [
  { id: 'all', label: 'Все заметки' }, { id: 'pinned', label: 'Закреплённые' },
  { id: 'recent', label: 'Недавние' }, { id: 'trash', label: 'Корзина' },
];

function linkMarkdown(link: NoteInsertion): string {
  return `[${link.title.replace(/[\\\[\]]/g, '\\$&')}](${link.href.replace(/\)/g, '%29')})`;
}

export function NotesWorkspace({ userId, compact = false, insertion, onInsertionConsumed }: {
  userId: string; compact?: boolean; insertion?: NoteInsertion | null; onInsertionConsumed?: () => void;
}) {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const urlNoteId = compact ? null : searchParams.get('note');
  const [view, setView] = useState<NoteView>('all');
  const [folderId, setFolderId] = useState<string | null>(null);
  const [sort, setSort] = useState<NoteSort>('updated');
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [page, setPage] = useState(1);
  const [selection, setSelection] = useState<{ id: string | null; urlNoteId: string | null } | null>(null);
  const selectedId = compact ? selection?.id ?? null : selection?.urlNoteId === urlNoteId ? selection.id : urlNoteId;
  const [addingFolder, setAddingFolder] = useState(false);
  const [folderName, setFolderName] = useState('');
  const [renamingFolder, setRenamingFolder] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  useEffect(() => { const timer = window.setTimeout(() => { setTerm(search.trim()); setPage(1); }, 300); return () => window.clearTimeout(timer); }, [search]);

  const params = { view, q: term, folderId, sort, page };
  const list = useQuery({ queryKey: queryKeys.notes.list(userId, params), queryFn: () => notesApi.list(params), staleTime: 15_000 });
  const folders = useQuery({ queryKey: queryKeys.notes.folders(userId), queryFn: notesApi.folders, staleTime: 60_000 });
  const detail = useQuery({ queryKey: queryKeys.notes.detail(userId, selectedId ?? ''), queryFn: () => notesApi.get(selectedId!), enabled: Boolean(selectedId), staleTime: 10_000 });

  const refresh = () => void queryClient.invalidateQueries({ queryKey: queryKeys.notes.all(userId) });
  const select = (id: string | null) => {
    setSelection({ id, urlNoteId });
    if (!compact) {
      const url = new URL(window.location.href);
      if (id) url.searchParams.set('note', id); else url.searchParams.delete('note');
      window.history.replaceState(null, '', `${url.pathname}${url.search}`);
    }
  };
  const create = useMutation({ mutationFn: notesApi.create, onSuccess: (note) => { setMessage(''); refresh(); select(note.id); onInsertionConsumed?.(); }, onError: () => setMessage('Не удалось создать заметку. Проверьте подключение и повторите попытку.') });
  const remove = useMutation({ mutationFn: notesApi.remove, onSuccess: () => { setMessage('Заметка перемещена в корзину.'); refresh(); select(null); }, onError: () => setMessage('Не удалось удалить заметку.') });
  const restore = useMutation({ mutationFn: notesApi.restore, onSuccess: () => { setMessage('Заметка восстановлена.'); refresh(); }, onError: () => setMessage('Не удалось восстановить заметку.') });
  const purge = useMutation({ mutationFn: notesApi.purge, onSuccess: () => { setMessage('Заметка удалена.'); refresh(); select(null); }, onError: () => setMessage('Не удалось удалить заметку.') });
  const addFolder = useMutation({ mutationFn: notesApi.createFolder, onSuccess: () => { setFolderName(''); setAddingFolder(false); void queryClient.invalidateQueries({ queryKey: queryKeys.notes.folders(userId) }); }, onError: () => setMessage('Не удалось создать папку. Возможно, такое название уже есть.') });
  const renameFolder = useMutation({ mutationFn: ({ id, name }: { id: string; name: string }) => notesApi.renameFolder(id, name), onSuccess: () => { setRenamingFolder(null); setFolderName(''); void queryClient.invalidateQueries({ queryKey: queryKeys.notes.folders(userId) }); }, onError: () => setMessage('Не удалось переименовать папку.') });
  const deleteFolder = useMutation({ mutationFn: notesApi.deleteFolder, onSuccess: () => { setFolderId(null); void queryClient.invalidateQueries({ queryKey: queryKeys.notes.folders(userId) }); refresh(); }, onError: () => setMessage('Не удалось удалить папку.') });
  const makeNote = (content = '') => create.mutate({ title: 'Новая заметка', content: insertion ? linkMarkdown(insertion) : content, folder_id: folderId });
  const chooseView = (next: NoteView) => { setView(next); setFolderId(null); setPage(1); select(null); };

  return <div className={`${styles.workspace} ${compact ? styles.compact : ''} ${selectedId ? styles.hasSelection : ''}`}>
    {!compact ? <div className={styles.pageHeading}><div><h1>Заметки</h1><p>Идеи, планы и полезные ссылки на вашу работу в CRM.</p></div><Button variant="primary" type="button" onClick={() => makeNote()} disabled={create.isPending}>+ Создать заметку</Button></div> : null}
    {insertion ? <div className={styles.insertionBanner}><span>Добавить ссылку: <strong>{insertion.title}</strong></span><small>Выберите заметку или создайте новую.</small></div> : null}
    {message ? <div className={styles.message} role="status">{message}<button type="button" onClick={() => setMessage('')} aria-label="Скрыть сообщение">×</button></div> : null}
    <div className={styles.columns}>
      <nav className={styles.navigation} aria-label="Навигация по заметкам">
        <div className={styles.navGroup}>{views.map((item) => <button type="button" key={item.id} className={view === item.id && !folderId ? styles.navActive : ''} onClick={() => chooseView(item.id)}>{item.label}</button>)}</div>
        <div className={styles.folderHeading}><strong>Папки</strong><button type="button" aria-label="Создать папку" onClick={() => { setAddingFolder(true); setFolderName(''); }}>+</button></div>
        {addingFolder ? <form className={styles.folderForm} onSubmit={(event) => { event.preventDefault(); if (folderName.trim()) addFolder.mutate(folderName.trim()); }}><Input aria-label="Название новой папки" placeholder="Название папки" value={folderName} onChange={(event) => setFolderName(event.target.value)} /><Button variant="ghost" size="s" type="submit" disabled={!folderName.trim() || addFolder.isPending}>Создать</Button></form> : null}
        <div className={styles.folderList}>{(folders.data ?? []).map((folder) => <div className={styles.folderRow} key={folder.id}>{renamingFolder === folder.id ? <form className={styles.folderForm} onSubmit={(event) => { event.preventDefault(); if (folderName.trim()) renameFolder.mutate({ id: folder.id, name: folderName.trim() }); }}><Input autoFocus aria-label="Новое название папки" value={folderName} onChange={(event) => setFolderName(event.target.value)} /><button type="submit" disabled={!folderName.trim()}>✓</button><button type="button" onClick={() => setRenamingFolder(null)}>×</button></form> : <><button type="button" className={folderId === folder.id ? styles.navActive : ''} onClick={() => { setView('all'); setFolderId(folder.id); setPage(1); select(null); }}>▣ {folder.name}</button><button type="button" className={styles.folderAction} aria-label={`Переименовать папку ${folder.name}`} onClick={() => { setRenamingFolder(folder.id); setFolderName(folder.name); }}>⋯</button><button type="button" className={styles.folderAction} aria-label={`Удалить папку ${folder.name}`} onClick={() => { if (window.confirm(`Удалить папку «${folder.name}»? Заметки останутся без папки.`)) deleteFolder.mutate(folder.id); }}>×</button></>}</div>)}</div>
      </nav>
      <section className={styles.noteList} aria-label="Список заметок">
        <div className={styles.listHeading}><strong>{folderId ? folders.data?.find((folder) => folder.id === folderId)?.name ?? 'Папка' : views.find((item) => item.id === view)?.label}</strong><Button variant="ghost" size="s" type="button" onClick={() => makeNote()} disabled={create.isPending || view === 'trash'}>+ Новая</Button></div>
        <div className={styles.listControls}><Input type="search" aria-label="Поиск по заметкам" placeholder="Поиск по заметкам..." value={search} onChange={(event) => setSearch(event.target.value)} /><Select aria-label="Сортировка заметок" value={sort} onChange={(event) => { setSort(event.target.value as NoteSort); setPage(1); }}><option value="updated">По дате</option><option value="title">По названию</option></Select></div>
        {list.isPending ? <p className={styles.listMessage}>Загрузка заметок...</p> : list.isError ? <div className={styles.listMessage}>Не удалось загрузить заметки. <Button variant="ghost" size="s" type="button" onClick={() => void list.refetch()}>Повторить</Button></div> : list.data?.items.length ? <div className={styles.noteRows}>{list.data.items.map((note) => <div className={`${styles.noteRow} ${selectedId === note.id ? styles.rowSelected : ''}`} key={note.id}><button type="button" className={styles.noteOpen} onClick={() => select(note.id)}><span className={styles.rowTitle}>{note.pinned ? <span aria-label="Закреплена">★ </span> : null}{note.title}</span><span className={styles.rowExcerpt}>{note.excerpt || 'Пустая заметка'}</span><span className={styles.rowMeta}>{new Date(note.updated_at).toLocaleDateString('ru-RU')} {note.folder_id ? `· ${folders.data?.find((folder) => folder.id === note.folder_id)?.name ?? ''}` : ''}</span></button>{view === 'trash' ? <div className={styles.rowActions}><button type="button" onClick={() => restore.mutate(note.id)}>Восстановить</button><button type="button" onClick={() => { if (window.confirm('Удалить заметку окончательно?')) purge.mutate(note.id); }}>Удалить</button></div> : <button type="button" className={styles.rowDelete} aria-label={`Удалить заметку ${note.title}`} onClick={() => remove.mutate(note.id)}>×</button>}</div>)}</div> : <div className={styles.listEmpty}><strong>{term ? 'Ничего не найдено' : view === 'trash' ? 'Корзина пуста' : 'Заметок пока нет'}</strong><p>{term ? 'Попробуйте другой запрос.' : 'Создайте заметку для идей, задач и ссылок на CRM.'}</p>{!term && view !== 'trash' ? <Button variant="primary" size="s" type="button" onClick={() => makeNote()}>Создать заметку</Button> : null}</div>}
        {list.data && list.data.total > list.data.page * list.data.page_size ? <Button variant="ghost" size="s" type="button" onClick={() => setPage((value) => value + 1)}>Следующая страница</Button> : null}{page > 1 ? <Button variant="ghost" size="s" type="button" onClick={() => setPage((value) => value - 1)}>Назад</Button> : null}
      </section>
      <div className={styles.editorColumn}>{selectedId && detail.data && detail.data.deleted_at === null ? <NotesEditor key={selectedId} note={detail.data} userId={userId} folders={folders.data ?? []} insertion={insertion} onInsertionConsumed={onInsertionConsumed} compact={compact} onBack={() => select(null)} onCreateCopy={(draft) => create.mutate({ title: `${draft.title || 'Без названия'} — копия`, content: draft.content, folder_id: draft.folder_id })} /> : selectedId && detail.isPending ? <div className={styles.editorEmpty}>Загрузка заметки...</div> : selectedId && detail.isError ? <div className={styles.editorEmpty}>Заметка недоступна. <Button variant="ghost" size="s" type="button" onClick={() => select(null)}>К списку</Button></div> : <div className={styles.editorEmpty}><span className={styles.emptySymbol}>✎</span><strong>{view === 'trash' ? 'Выберите заметку для восстановления' : 'Выберите заметку'}</strong><p>Откройте запись из списка или создайте новую.</p>{view !== 'trash' ? <Button variant="primary" size="s" type="button" onClick={() => makeNote()}>Создать заметку</Button> : null}</div>}</div>
    </div>
  </div>;
}
