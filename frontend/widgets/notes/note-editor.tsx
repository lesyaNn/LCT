'use client';

import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { EditorContent, useEditor } from '@tiptap/react';
import type { ChainedCommands, Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from '@tiptap/markdown';
import { TaskItem, TaskList } from '@tiptap/extension-list';
import Link from '@tiptap/extension-link';
import { TableKit } from '@tiptap/extension-table';
import Image from '@tiptap/extension-image';
import Placeholder from '@tiptap/extension-placeholder';
import { Input } from '@/shared/ui/rtk/form-controls';
import { Button } from '@/shared/ui/rtk/button';
import { Icon } from '@/shared/ui/rtk/icon';
import { mentionHref, noteApi, type Mention, type MentionKind } from '@/shared/lib/notes-repository';
import styles from './notes.module.css';

type Range = { from: number; to: number };
type Anchor = { left: number; top: number; bottom: number };
type Slash = Range & { query: string };
const commands = [
  ['h1', 'Заголовок 1'], ['h2', 'Заголовок 2'], ['h3', 'Заголовок 3'],
  ['bullet', 'Маркированный список'], ['numbered', 'Нумерованный список'],
  ['todo', 'Чек-лист'], ['quote', 'Цитата'], ['code', 'Код'],
  ['divider', 'Разделитель'], ['link', 'Ссылка'],
  ['user', 'Пользователь CRM'], ['university', 'Вузы'], ['direction', 'ИТ-направления'],
  ['program', 'ИТ-программы'], ['vendor', 'Вендоры'], ['product', 'ИТ-продукты'],
  ['agreements', 'Договоры и лицензии'], ['responsible', 'Ответственные'],
] as const;
const pickerLabels: Partial<Record<MentionKind, string>> = {
  user: 'Пользователи CRM', university: 'Вузы', direction: 'ИТ-направления', program: 'ИТ-программы',
  vendor: 'Вендоры', product: 'ИТ-продукты', agreements: 'Договоры и лицензии', responsible: 'Ответственные',
};
const icons = { user: 'user', university: 'university', direction: 'admin', program: 'admin', vendor: 'admin', workflow: 'workflow', document: 'docs', contract: 'docs', license: 'docs', product: 'admin', responsible: 'user' } as const;
const kindLabels = { user: 'Пользователь', university: 'Вуз', direction: 'ИТ-направление', program: 'ИТ-программа', vendor: 'Вендор', workflow: 'Workflow', document: 'Документ', contract: 'Договор', license: 'Лицензия', product: 'ИТ-продукт', responsible: 'Ответственный' };

const ReferenceLink = Link.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      noteReference: {
        default: null,
        parseHTML: () => null,
        renderHTML: (attributes) => typeof attributes.href === 'string' && attributes.href.startsWith('/notes/reference?') ? { 'data-note-reference': 'true' } : {},
      },
    };
  },
});

/** Scroll the popup's list only; never move the CRM page to reveal an option. */
function revealOption(element: HTMLButtonElement | null) {
  const list = element?.parentElement;
  if (!element || !list) return;
  const top = element.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
  if (top < list.scrollTop) list.scrollTop = top;
  else if (top + element.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = top + element.offsetHeight - list.clientHeight;
}

export function NoteEditor({ initialValue, onChange, onReady }: { initialValue: string; onChange: (value: string) => void; onReady: (editor: Editor | null) => void }) {
  const router = useRouter();
  const root = useRef<HTMLDivElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const linkInput = useRef<HTMLInputElement>(null);
  const panelOpen = useRef(false);
  const onChangeRef = useRef(onChange);
  const handlers = useRef<{ detect: (editor: Editor) => void; key: (event: KeyboardEvent) => boolean; paste: (event: ClipboardEvent) => boolean }>({ detect: () => undefined, key: () => false, paste: () => false });
  const [slash, setSlash] = useState<Slash | null>(null);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [picker, setPicker] = useState<(Range & { kind: MentionKind }) | null>(null);
  const [link, setLink] = useState<(Range & { label: string; url: string }) | null>(null);
  const [linkError, setLinkError] = useState('');
  const [entityQuery, setEntityQuery] = useState('');
  const [entities, setEntities] = useState<Mention[]>([]);
  const [entityLoading, setEntityLoading] = useState(false);
  const [entityError, setEntityError] = useState(false);
  const [choice, setChoice] = useState(0);
  const [referenceMessage, setReferenceMessage] = useState('');
  const [resolving, setResolving] = useState(false);
  const menuId = useId();
  const filtered = slash ? commands.filter(([key, label]) => key.includes(slash.query.toLowerCase()) || label.toLocaleLowerCase('ru').includes(slash.query.toLocaleLowerCase('ru'))) : [];
  const editor = useEditor({
    immediatelyRender: false,
    shouldRerenderOnTransaction: true,
    extensions: [
      StarterKit.configure({ link: false, underline: false, heading: { levels: [1, 2, 3] } }),
      ReferenceLink.configure({ openOnClick: false, HTMLAttributes: { target: null, rel: 'noopener noreferrer' } }),
      TaskList, TaskItem.configure({ nested: true }), TableKit, Image,
      Placeholder.configure({ placeholder: 'Начните писать или введите /' }), Markdown,
    ],
    content: initialValue,
    contentType: 'markdown',
    editorProps: {
      attributes: { class: styles.noteInput, role: 'textbox', 'aria-label': 'Текст заметки', 'aria-multiline': 'true', spellcheck: 'true' },
      handleKeyDown: (_view, event) => handlers.current.key(event),
      handlePaste: (_view, event) => handlers.current.paste(event),
    },
    onUpdate: ({ editor }) => { onChangeRef.current(editor.getMarkdown()); handlers.current.detect(editor); },
    onSelectionUpdate: ({ editor }) => handlers.current.detect(editor),
    onBlur: () => setSlash(null),
  });

  useLayoutEffect(() => { onChangeRef.current = onChange; }, [onChange]);
  useEffect(() => { onReady(editor); return () => onReady(null); }, [editor, onReady]);
  useLayoutEffect(() => { handlers.current = { detect: detectSlash, key: onEditorKey, paste: onPaste }; });
  const linkOpened = Boolean(link);
  useLayoutEffect(() => {
    if (picker) searchInput.current?.focus({ preventScroll: true });
    else if (linkOpened) linkInput.current?.focus({ preventScroll: true });
  }, [picker, linkOpened]);

  useEffect(() => {
    if (!picker) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setEntityLoading(true); setEntityError(false);
      const result = await noteApi.mentions(picker.kind, entityQuery, controller.signal);
      if (controller.signal.aborted) return;
      setEntities(result.ok ? result.data : []); setEntityError(!result.ok); setEntityLoading(false);
    }, 200);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [picker, entityQuery]);

  const opened = Boolean(slash || picker || link);
  useEffect(() => {
    if (!opened || !editor) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!popup.current?.contains(target) && !root.current?.contains(target)) closeMenus();
    };
    const reposition = (event: Event) => {
      if (event.target instanceof Node && popup.current?.contains(event.target)) return;
      placePopup(editor);
    };
    document.addEventListener('pointerdown', outside);
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('scroll', reposition, true); window.removeEventListener('resize', reposition); };
  }, [opened, editor]);

  function closeMenus() { panelOpen.current = false; setSlash(null); setPicker(null); setLink(null); }
  function placePopup(current: Editor) {
    const rect = current.view.coordsAtPos(current.state.selection.from);
    setAnchor({ left: rect.left, top: rect.top, bottom: rect.bottom });
  }
  function focus() { editor?.commands.focus(undefined, { scrollIntoView: false }); }
  function detectSlash(current: Editor) {
    if (panelOpen.current) return;
    const { $from, empty } = current.state.selection;
    if (!empty || $from.parent.type.spec.code) { setSlash(null); return; }
    const match = $from.parent.textBetween(0, $from.parentOffset, '\n', '\ufffc').match(/(?:^|\s)\/([^/\s]*)$/);
    if (!match) { setSlash(null); return; }
    setSlash({ from: $from.pos - match[1].length - 1, to: $from.pos, query: match[1] });
    setChoice(0); placePopup(current);
  }
  function run(action: (chain: ChainedCommands) => ChainedCommands) {
    if (!editor) return;
    closeMenus(); action(editor.chain().focus(undefined, { scrollIntoView: false })).run();
  }
  function openLink(range?: Range) {
    if (!editor) return;
    const selection = range ?? editor.state.selection;
    placePopup(editor); panelOpen.current = true; setSlash(null); setLinkError('');
    setLink({ from: selection.from, to: selection.to, label: range ? '' : editor.state.doc.textBetween(selection.from, selection.to), url: range ? '' : editor.getAttributes('link').href || '' });
  }
  function insertLink(range: Range, label: string, href: string) {
    if (!editor) return;
    const marks = editor.state.doc.resolve(range.from).marks().filter((mark) => mark.type.name !== 'link').map((mark) => mark.toJSON());
    closeMenus();
    editor.chain().focus(undefined, { scrollIntoView: false }).insertContentAt(range, { type: 'text', text: label, marks: [...marks, { type: 'link', attrs: { href } }] }).unsetMark('link').run();
  }
  function chooseCommand(index: number) {
    const command = filtered[index];
    if (!slash || !editor || !command) return;
    const [key] = command;
    if (key === 'user' || key === 'university' || key === 'direction' || key === 'program' || key === 'vendor' || key === 'product' || key === 'agreements' || key === 'responsible') {
      panelOpen.current = true; setPicker({ from: slash.from, to: slash.to, kind: key });
      setEntityQuery(''); setEntities([]); setEntityLoading(true); setChoice(0); setSlash(null); return;
    }
    if (key === 'link') { openLink(slash); return; }
    const chain = editor.chain().focus(undefined, { scrollIntoView: false }).deleteRange(slash);
    closeMenus();
    if (key === 'h1' || key === 'h2' || key === 'h3') chain.setHeading({ level: Number(key[1]) as 1 | 2 | 3 }).run();
    else if (key === 'bullet') chain.toggleBulletList().run();
    else if (key === 'numbered') chain.toggleOrderedList().run();
    else if (key === 'todo') chain.toggleTaskList().run();
    else if (key === 'quote') chain.toggleBlockquote().run();
    else if (key === 'code') chain.toggleCodeBlock().run();
    else if (key === 'divider') chain.setHorizontalRule().run();
  }
  function chooseEntity(index: number) {
    const entity = entities[index];
    if (picker && entity) insertLink(picker, entity.title, mentionHref(entity));
  }
  function menuKeys(event: KeyboardEvent | ReactKeyboardEvent, length: number, choose: (index: number) => void) {
    if (event.key === 'Escape') { event.preventDefault(); closeMenus(); focus(); return true; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); setChoice((index) => length ? (index + (event.key === 'ArrowDown' ? 1 : length - 1)) % length : 0); return true;
    }
    if (event.key === 'Enter') { event.preventDefault(); choose(choice); return true; }
    return false;
  }
  function onEditorKey(event: KeyboardEvent) {
    if (event.isComposing) return false;
    if (slash && menuKeys(event, filtered.length, chooseCommand)) return true;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); event.stopPropagation(); openLink(); return true;
    }
    return false;
  }
  function onPaste(event: ClipboardEvent) {
    if (!editor || editor.state.selection.$from.parent.type.spec.code || event.clipboardData?.getData('text/html')) return false;
    const text = event.clipboardData?.getData('text/plain') || '';
    if (!/(?:^|\n)\s*(?:#{1,6}\s|[-*+]\s|\d+\.\s|>|`{3}|~{3}|---)|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)/.test(text)) return false;
    editor.commands.insertContent(text, { contentType: 'markdown' });
    return true;
  }
  async function openReference(href: string) {
    if (resolving) return;
    setResolving(true); setReferenceMessage('');
    const result = await noteApi.resolve(href.split('?')[1]);
    setResolving(false);
    if (!result.ok) { setReferenceMessage(result.status === 404 ? 'Объект удалён или недоступен' : 'Не удалось проверить доступ. Повторите попытку.'); return; }
    if (!result.data[0]) { setReferenceMessage('Объект удалён или недоступен'); return; }
    const target = result.data[0].href;
    if (target) router.push(target);
    else setReferenceMessage('Карточка объекта недоступна для вашей роли');
  }

  const width = anchor && typeof window !== 'undefined' ? Math.min(390, window.innerWidth - 24) : 390;
  const below = anchor && typeof window !== 'undefined' ? window.innerHeight - anchor.bottom - 14 : 320;
  const above = anchor ? anchor.top - 14 : 320;
  const showAbove = below < 240 && above > below;
  const popupStyle = anchor ? {
    width, left: Math.max(12, Math.min(anchor.left, window.innerWidth - width - 12)),
    ...(showAbove ? { bottom: window.innerHeight - anchor.top + 6 } : { top: anchor.bottom + 6 }),
    maxHeight: Math.max(120, Math.min(360, showAbove ? above : below)),
  } : undefined;

  return <div ref={root} className={styles.editor}>
    <div className={styles.editorControls}>
      <div className={styles.toolbar} role="toolbar" aria-label="Форматирование Markdown" onMouseDown={(event) => event.preventDefault()}>
        <button type="button" title="Жирный (Ctrl/⌘ B)" aria-label="Жирный" aria-pressed={editor?.isActive('bold') || false} onClick={() => run((chain) => chain.toggleBold())}><b>B</b></button>
        <button type="button" title="Курсив (Ctrl/⌘ I)" aria-label="Курсив" aria-pressed={editor?.isActive('italic') || false} onClick={() => run((chain) => chain.toggleItalic())}><i>I</i></button>
        <button type="button" title="Зачёркнутый" aria-label="Зачёркнутый" aria-pressed={editor?.isActive('strike') || false} onClick={() => run((chain) => chain.toggleStrike())}><s>S</s></button>
        {([1, 2, 3] as const).map((level) => <button type="button" key={level} aria-label={`Заголовок ${level}`} aria-pressed={editor?.isActive('heading', { level }) || false} onClick={() => run((chain) => chain.toggleHeading({ level }))}>H{level}</button>)}
        <button type="button" aria-label="Маркированный список" title="Маркированный список" onClick={() => run((chain) => chain.toggleBulletList())}>• ≡</button>
        <button type="button" aria-label="Нумерованный список" title="Нумерованный список" onClick={() => run((chain) => chain.toggleOrderedList())}>1.</button>
        <button type="button" aria-label="Чек-лист" title="Чек-лист" onClick={() => run((chain) => chain.toggleTaskList())}>☑</button>
        <button type="button" aria-label="Цитата" title="Цитата" onClick={() => run((chain) => chain.toggleBlockquote())}>❞</button>
        <button type="button" aria-label="Блок кода" title="Код" onClick={() => run((chain) => chain.toggleCodeBlock())}>{'<>'}</button>
        <button type="button" aria-label="Разделитель" title="Разделитель" onClick={() => run((chain) => chain.setHorizontalRule())}>―</button>
        <button type="button" aria-label="Ссылка" title="Ссылка (Ctrl/⌘ K)" onClick={() => openLink()}>↗</button>
      </div>
    </div>
    {referenceMessage ? <p className={styles.referenceMessage} role="status">{referenceMessage}</p> : null}
    <EditorContent editor={editor} onFocus={() => { if (panelOpen.current) closeMenus(); }} onClickCapture={(event) => {
      const target = (event.target as HTMLElement).closest('a');
      if (!target) return;
      const href = target.getAttribute('href') || '';
      if (href.startsWith('/notes/reference?')) { event.preventDefault(); event.stopPropagation(); void openReference(href); }
      else if (event.metaKey || event.ctrlKey) { event.preventDefault(); window.open(href, '_blank', 'noopener,noreferrer'); }
    }} />
    {opened && anchor && typeof document !== 'undefined' ? createPortal(<div ref={popup} className={styles.editorPopover} style={popupStyle}>
      {slash ? <div id={menuId} className={styles.commandMenu} role="listbox" aria-label="Команды редактора">
        {filtered.length ? filtered.map(([key, label], index) => <button type="button" role="option" id={`${menuId}-${index}`} aria-selected={choice === index} key={key} ref={(element) => { if (choice === index) revealOption(element); }} onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => setChoice(index)} onClick={() => chooseCommand(index)}><strong>/{key}</strong><span>{label}</span></button>) : <p>Команда не найдена</p>}
      </div> : null}
      {picker ? <div className={styles.insertPanel} role="region" aria-label="Вставка упоминания">
        <div className={styles.inlineHeader}><strong>{pickerLabels[picker.kind] ?? 'Сущности CRM'}</strong><button type="button" aria-label="Закрыть выбор сущности" onClick={() => { closeMenus(); focus(); }}>×</button></div>
        <Input ref={searchInput} aria-label="Поиск сущности" placeholder="Название или имя…" value={entityQuery} maxLength={100} onChange={(event) => { setEntityQuery(event.target.value); setChoice(0); setEntities([]); setEntityLoading(true); }} onKeyDown={(event) => menuKeys(event, entities.length, chooseEntity)} role="combobox" aria-autocomplete="list" aria-expanded aria-controls={`${menuId}-entities`} aria-activedescendant={entities[choice] ? `${menuId}-entity-${choice}` : undefined} />
        <div id={`${menuId}-entities`} role="listbox" className={styles.entityResults} aria-label="Найденные сущности">
          {entityLoading ? <p role="status">Поиск…</p> : entityError ? <p role="alert">Не удалось загрузить сущности. Измените запрос, чтобы повторить.</p> : !entities.length ? <p>Нет доступных совпадений</p> : null}
          {entities.map((entity, index) => <button type="button" key={`${entity.kind}-${entity.id}-${entity.university_id}`} role="option" id={`${menuId}-entity-${index}`} aria-selected={choice === index} onMouseEnter={() => setChoice(index)} onClick={() => chooseEntity(index)} ref={(element) => { if (choice === index) revealOption(element); }}><Icon name={icons[entity.kind]} size={18} /><span><strong>{entity.title}</strong><small>{kindLabels[entity.kind]}{entity.subtitle ? ` · ${entity.subtitle}` : ''}</small></span></button>)}
        </div>
      </div> : null}
      {link ? <form className={styles.insertPanel} onSubmit={(event) => {
        event.preventDefault();
        if (!/^(https?:\/\/|mailto:)/i.test(link.url)) { setLinkError('Введите ссылку с https://, http:// или mailto:'); return; }
        insertLink(link, link.label || link.url, link.url);
      }} onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); closeMenus(); focus(); } }}>
        <div className={styles.inlineHeader}><strong>Вставить ссылку</strong><button type="button" aria-label="Закрыть вставку ссылки" onClick={() => { closeMenus(); focus(); }}>×</button></div>
        <Input aria-label="Текст ссылки" placeholder="Текст ссылки" value={link.label} onChange={(event) => setLink({ ...link, label: event.target.value })} />
        <Input ref={linkInput} aria-label="Адрес ссылки" placeholder="https://" value={link.url} onChange={(event) => setLink({ ...link, url: event.target.value })} />
        {linkError ? <p role="alert">{linkError}</p> : null}<Button size="s" type="submit">Вставить</Button>
      </form> : null}
    </div>, document.body) : null}
  </div>;
}
