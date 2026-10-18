'use client';

import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ApiRequestError } from '@/shared/lib/api-errors';
import { notesApi, type Note, type NoteFolder, type NoteLinkOption } from '@/shared/lib/notes-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { Button } from '@/shared/ui/rtk/button';
import { Input, Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { Icon } from '@/shared/ui/rtk/icon';
import type { IconName } from '@/shared/types/navigation';
import type { NoteInsertion } from './notes-launcher';
import { useNotesLauncher } from './notes-launcher';
import styles from './notes.module.css';

type Draft = { title: string; content: string; pinned: boolean; folder_id: string | null };
type SaveState = 'saved' | 'unsaved' | 'saving' | 'error' | 'conflict';

function draftFromNote(note: Note): Draft {
  return { title: note.title, content: note.content, pinned: note.pinned, folder_id: note.folder_id };
}

function sameDraft(left: Draft, right: Draft): boolean {
  return left.title === right.title && left.content === right.content && left.pinned === right.pinned && left.folder_id === right.folder_id;
}

function safeMarkdownUrl(url: string): string {
  if (url.startsWith('/') && !url.startsWith('//')) return url;
  try { const parsed = new URL(url); return ['https:', 'http:', 'mailto:'].includes(parsed.protocol) ? url : ''; }
  catch { return ''; }
}

function markdownLink(option: { title: string; href: string }): string {
  return `[${option.title.replace(/[\\\[\]]/g, '\\$&')}](${option.href.replace(/\)/g, '%29')})`;
}

function linkedPaths(content: string): string[] {
  return [...new Set([...content.matchAll(/\]\((\/[^\s)]+)\)/g)].map((match) => match[1]))].slice(0, 50);
}

function crmIcon(href: string): IconName {
  if (href.startsWith('/workflows')) return 'workflow';
  if (href.includes('document=')) return 'docs';
  if (href.startsWith('/universities')) return 'university';
  if (href.startsWith('/reports')) return 'report';
  if (href.startsWith('/notes')) return 'notes';
  return 'dashboard';
}

const linkKindLabels: Record<string, string> = {
  university: 'Вуз', workflow: 'Workflow', stage: 'Этап Workflow',
  document: 'Документ', meeting: 'Встреча', note: 'Заметка', section: 'Раздел CRM',
};

function LinkPicker({ onSelect, onClose }: { onSelect: (option: NoteLinkOption) => void; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [term, setTerm] = useState('');
  const [kind, setKind] = useState('all');
  useEffect(() => { const timer = window.setTimeout(() => setTerm(query.trim()), 250); return () => window.clearTimeout(timer); }, [query]);
  const results = useQuery({ queryKey: ['notes', 'link-options', term], queryFn: () => notesApi.linkOptions(term), enabled: term.length >= 2, staleTime: 30_000 });
  const options = (results.data ?? []).filter((option) => kind === 'all' || option.kind === kind);
  return <div className={styles.linkPicker} role="group" aria-label="Добавить ссылку на объект CRM">
    <div className={styles.pickerHeading}><strong>Ссылка на объект CRM</strong><button type="button" onClick={onClose} aria-label="Закрыть поиск объектов">×</button></div>
    <div className={styles.pickerFilters}><Select aria-label="Тип объекта" value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">Все объекты</option><option value="university">Вузы</option><option value="workflow">Workflow</option><option value="stage">Этапы</option><option value="document">Документы</option><option value="meeting">Встречи</option><option value="note">Заметки</option><option value="section">Разделы</option></Select><Input autoFocus type="search" aria-label="Найти объект" placeholder="Название объекта..." value={query} onChange={(event) => setQuery(event.target.value)} /></div>
    <div className={styles.pickerResults}>{term.length < 2 ? <p>Введите минимум два символа.</p> : results.isPending ? <p>Поиск...</p> : results.isError ? <p>Не удалось найти объекты. Повторите поиск.</p> : options.length ? options.map((option) => <button type="button" key={option.href} onClick={() => onSelect(option)}><strong>{option.title}</strong><small>{option.subtitle ?? linkKindLabels[option.kind] ?? 'Объект CRM'}</small></button>) : <p>Доступных объектов не найдено.</p>}</div>
  </div>;
}

export function NotesEditor({ note, userId, folders, insertion, onInsertionConsumed, onCreateCopy, onBack, compact = false }: {
  note: Note; userId: string; folders: NoteFolder[]; insertion?: NoteInsertion | null;
  onInsertionConsumed?: () => void; onCreateCopy: (draft: Draft) => void; onBack?: () => void; compact?: boolean;
}) {
  const notesLauncher = useNotesLauncher();
  const queryClient = useQueryClient();
  const recoveryKey = `rtk-note-draft:${userId}:${note.id}`;
  const recovery = useMemo(() => {
    if (typeof window === 'undefined') return null;
    try {
      const raw = window.sessionStorage.getItem(recoveryKey);
      if (!raw) return null;
      const value = JSON.parse(raw) as { draft: Draft; revision: number };
      return value?.draft && typeof value.draft.content === 'string' && typeof value.draft.title === 'string' ? value : null;
    } catch { return null; }
  }, [recoveryKey]);
  const recoveryDirty = Boolean(recovery && !sameDraft(recovery.draft, draftFromNote(note)));
  const [draft, setDraft] = useState<Draft>(recovery?.draft ?? draftFromNote(note));
  const draftRef = useRef(draft);
  const savedRef = useRef(draftFromNote(note));
  const revisionRef = useRef(note.revision);
  const hasRecoveryConflict = Boolean(recoveryDirty && recovery?.revision !== note.revision);
  const conflictRef = useRef(hasRecoveryConflict);
  const [saveState, setSaveState] = useState<SaveState>(hasRecoveryConflict ? 'conflict' : recoveryDirty ? 'unsaved' : 'saved');
  const runningRef = useRef<Promise<void> | null>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const handledInsertion = useRef<number | null>(null);
  const [preview, setPreview] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const hrefs = useMemo(() => linkedPaths(draft.content), [draft.content]);
  const resolved = useQuery({ queryKey: queryKeys.notes.links(userId, hrefs), queryFn: () => notesApi.resolveLinks(hrefs), enabled: hrefs.length > 0, staleTime: 30_000 });
  const resolvedMap = useMemo(() => new Map((resolved.data ?? []).map((item) => [item.href, item])), [resolved.data]);

  const change = useCallback((next: Draft) => {
    draftRef.current = next;
    setDraft(next);
    setSaveState(conflictRef.current ? 'conflict' : 'unsaved');
    try { window.sessionStorage.setItem(recoveryKey, JSON.stringify({ draft: next, revision: revisionRef.current })); } catch { /* the backend remains the source of truth */ }
  }, [recoveryKey]);

  const persist = useCallback((): Promise<void> => {
    if (conflictRef.current) return Promise.resolve();
    if (runningRef.current) return runningRef.current;
    const work = (async () => {
      while (!sameDraft(draftRef.current, savedRef.current)) {
        const snapshot = { ...draftRef.current };
        setSaveState('saving');
        let result: Note;
        try { result = await notesApi.update(note.id, { revision: revisionRef.current, ...snapshot }); }
        catch (error) {
          if (error instanceof ApiRequestError && error.status === 409) { conflictRef.current = true; setSaveState('conflict'); }
          else setSaveState('error');
          return;
        }
        revisionRef.current = result.revision;
        savedRef.current = draftFromNote(result);
        queryClient.setQueryData(queryKeys.notes.detail(userId, note.id), result);
        void queryClient.invalidateQueries({ queryKey: queryKeys.notes.all(userId), exact: false, refetchType: 'active' });
      }
      try { window.sessionStorage.removeItem(recoveryKey); } catch { /* optional recovery cache */ }
      setSaveState('saved');
    })();
    runningRef.current = work;
    void work.finally(() => { runningRef.current = null; });
    return work;
  }, [note.id, queryClient, recoveryKey, userId]);

  useEffect(() => {
    if (sameDraft(draft, savedRef.current) || conflictRef.current) return;
    const timer = window.setTimeout(() => { void persist(); }, 750);
    return () => window.clearTimeout(timer);
  }, [draft, persist]);
  useEffect(() => () => { void persist(); }, [persist]);

  const insert = useCallback((snippet: string, prefix = '', suffix = '') => {
    const field = textRef.current;
    const start = field?.selectionStart ?? draftRef.current.content.length;
    const end = field?.selectionEnd ?? start;
    const selected = draftRef.current.content.slice(start, end);
    const replacement = `${prefix}${selected || snippet}${suffix}`;
    change({ ...draftRef.current, content: draftRef.current.content.slice(0, start) + replacement + draftRef.current.content.slice(end) });
    setPreview(false);
    requestAnimationFrame(() => { field?.focus(); field?.setSelectionRange(start + prefix.length, start + replacement.length - suffix.length); });
  }, [change]);

  useEffect(() => {
    if (!insertion || handledInsertion.current === insertion.key) return;
    handledInsertion.current = insertion.key;
    insert(`\n${markdownLink(insertion)}\n`);
    onInsertionConsumed?.();
  }, [insertion, insert, onInsertionConsumed]);

  const statusText = { saved: 'Сохранено', unsaved: 'Есть изменения', saving: 'Сохранение…', error: 'Не удалось сохранить', conflict: 'Заметка изменена в другом окне' }[saveState];
  return <section className={`${styles.editor} ${compact ? styles.editorCompact : ''}`} aria-label="Редактор заметки">
    <div className={styles.editorTop}>{onBack ? <Button variant="ghost" size="s" type="button" onClick={onBack}>← К списку</Button> : null}<span className={`${styles.saveState} ${saveState === 'error' || saveState === 'conflict' ? styles.saveError : ''}`} role="status">{statusText}</span>{saveState === 'error' ? <Button variant="ghost" size="s" type="button" onClick={() => void persist()}>Повторить</Button> : null}{saveState === 'conflict' ? <Button variant="ghost" size="s" type="button" onClick={() => onCreateCopy(draftRef.current)}>Сохранить копию</Button> : null}</div>
    <Input className={styles.titleInput} aria-label="Название заметки" placeholder="Без названия" maxLength={256} value={draft.title} onChange={(event) => change({ ...draftRef.current, title: event.target.value })} />
    <div className={styles.noteMeta}><button type="button" className={styles.metaButton} onClick={() => change({ ...draftRef.current, pinned: !draftRef.current.pinned })}>{draft.pinned ? '★ Закреплена' : '☆ Закрепить'}</button><Select aria-label="Папка заметки" value={draft.folder_id ?? ''} onChange={(event) => change({ ...draftRef.current, folder_id: event.target.value || null })}><option value="">Без папки</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</Select><span>Изменена {new Date(note.updated_at).toLocaleDateString('ru-RU')}</span></div>
    <div className={styles.toolbar} role="toolbar" aria-label="Форматирование заметки">
      <button type="button" title="Заголовок" onClick={() => insert('Заголовок', '## ')}>H2</button>
      <button type="button" title="Жирный (Ctrl+B)" onClick={() => insert('важный текст', '**', '**')}><b>Ж</b></button>
      <button type="button" title="Курсив (Ctrl+I)" onClick={() => insert('курсив', '*', '*')}><i>К</i></button>
      <button type="button" title="Маркированный список" onClick={() => insert('Пункт списка', '- ')}>•</button>
      <button type="button" title="Чек-лист" onClick={() => insert('Задача', '- [ ] ')}>☑</button>
      <button type="button" title="Ссылка" onClick={() => insert('текст ссылки', '[', '](https://)')}>↗</button>
      <button type="button" className={styles.objectButton} onClick={() => setPickerOpen((value) => !value)}>+ Объект CRM</button>
      <details className={styles.moreTools}><summary>Ещё</summary><div><button type="button" onClick={() => insert('Заголовок', '# ')}>H1</button><button type="button" onClick={() => insert('Подзаголовок', '### ')}>H3</button><button type="button" onClick={() => insert('Пункт списка', '1. ')}>Нумерованный список</button><button type="button" onClick={() => insert('цитата', '> ')}>Цитата</button><button type="button" onClick={() => insert('зачёркнутый текст', '~~', '~~')}>Зачёркнутый</button><button type="button" onClick={() => insert('код', '`', '`')}>Код</button><button type="button" onClick={() => insert('\n---\n')}>Разделитель</button></div></details>
      <button type="button" className={styles.previewButton} aria-pressed={preview} onClick={() => setPreview((value) => !value)}>{preview ? 'Редактировать' : 'Просмотр'}</button>
    </div>
    {pickerOpen ? <LinkPicker onClose={() => setPickerOpen(false)} onSelect={(option) => { insert(markdownLink(option)); setPickerOpen(false); }} /> : null}
    {preview ? <div className={styles.preview} aria-label="Предпросмотр заметки"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={safeMarkdownUrl} components={{ img: ({ alt }) => <span>{alt ? `[Изображение: ${alt}]` : '[Изображение]'}</span>, a: ({ href, children }) => {
      if (!href) return <span>{children}</span>;
      if (href.startsWith('/')) {
        const target = resolvedMap.get(href);
        if (!target?.available) return <span className={styles.unavailableLink} title={resolved.isPending ? 'Проверка доступа…' : 'Объект удалён или недоступен'}>{resolved.isPending ? 'Проверка ссылки…' : 'Объект недоступен'}</span>;
        return <Link href={href} className={styles.crmLink} title={target.title ?? undefined} onClick={() => notesLauncher?.close()}><span aria-hidden="true"><Icon name={crmIcon(href)} size={16} /></span>{children}<span aria-hidden="true">↗</span></Link>;
      }
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    } }}>{draft.content || '*Начните писать…*'}</ReactMarkdown></div> : <TextArea ref={textRef} className={styles.bodyInput} aria-label="Содержимое заметки" placeholder="Начните писать..." value={draft.content} onChange={(event) => change({ ...draftRef.current, content: event.target.value })} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); void persist(); } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'b') { event.preventDefault(); insert('жирный текст', '**', '**'); } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'i') { event.preventDefault(); insert('курсив', '*', '*'); } }} />}
    {hrefs.length ? <div className={styles.related}><strong>Связанные объекты</strong>{hrefs.map((href) => { const target = resolvedMap.get(href); return target?.available ? <Link key={href} href={href} onClick={() => notesLauncher?.close()}><span aria-hidden="true"><Icon name={crmIcon(href)} size={14} /></span>{target.title} ↗</Link> : <span key={href} className={styles.unavailableLink}>{resolved.isPending ? 'Проверка…' : 'Объект недоступен'}</span>; })}</div> : null}
  </section>;
}
