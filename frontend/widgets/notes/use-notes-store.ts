'use client';

import { useEffect, useMemo, useReducer } from 'react';
import { noteApi, type Note } from '@/shared/lib/notes-repository';

export type Draft = { note: Note; dirty: boolean; creating?: boolean; saving?: boolean; error?: string; remote?: Note; conflict?: boolean; missing?: boolean; editorKey?: number };

/** One serialized save queue per note. Drafts survive route changes and reloads. */
class NotesStore {
  entries = new Map<string, Draft>();
  timers = new Map<string, ReturnType<typeof setTimeout>>();
  listeners = new Set<() => void>();
  storageError = false;
  ready = false;
  constructor(readonly owner: string) {}
  get key() { return `crm:notes:drafts:${this.owner}`; }
  emit = () => { this.listeners.forEach((listener) => listener()); };
  persist() {
    const value = JSON.stringify([...this.entries.values()].filter((entry) => entry.dirty).map(({ note, dirty, creating }) => ({ note, dirty, creating })));
    let stored = false;
    // The tab-specific copy prevents another tab's save from clearing this
    // tab's offline work. Local storage also provides recovery after closing.
    try { sessionStorage.setItem(this.key, value); stored = true; } catch { /* fallback below */ }
    try { localStorage.setItem(this.key, value); stored = true; } catch { /* keep the tab-specific copy */ }
    this.storageError = !stored;
    this.emit();
  }
  init() {
    if (this.ready) return;
    this.ready = true;
    try {
      let cached: string | null = null;
      try { cached = sessionStorage.getItem(this.key); } catch { /* use the durable copy */ }
      if (cached === null) cached = localStorage.getItem(this.key);
      const raw: unknown = JSON.parse(cached || '[]');
      if (Array.isArray(raw)) for (const entry of raw) {
        const note = entry?.note;
        if (note && typeof note.id === 'string' && typeof note.title === 'string' && typeof note.content === 'string' && Number.isInteger(note.revision)) {
          this.entries.set(note.id, { note, dirty: true, creating: Boolean(entry.creating) });
        }
      }
    } catch { this.storageError = true; }
    this.emit();
    this.retryAll();
  }
  schedule(id: string, delay = 650) {
    clearTimeout(this.timers.get(id));
    if (!this.listeners.size) return;
    this.timers.set(id, setTimeout(() => { this.timers.delete(id); void this.save(id); }, delay));
  }
  edit(id: string, changes: Partial<Pick<Note, 'title' | 'content'>>) {
    const entry = this.entries.get(id);
    if (!entry) return;
    entry.note = { ...entry.note, ...changes };
    entry.dirty = true;
    this.persist();
    if (!entry.conflict && !entry.missing) this.schedule(id);
  }
  create(title = '', content = '') {
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    this.entries.set(id, { note: { id, title, content, revision: 0, created_at: now, updated_at: now }, dirty: true, creating: true });
    this.persist();
    void this.save(id);
    return id;
  }
  async open(id: string) {
    if (this.entries.get(id)?.creating) return;
    const result = await noteApi.get(id);
    const entry = this.entries.get(id);
    if (!result.ok) {
      if (entry) {
        if (result.status === 404 && !entry.creating) { entry.missing = true; entry.error = 'Заметка удалена. Ваш текст сохранён в черновике.'; }
        else if (!entry.creating) entry.error = 'Не удалось загрузить заметку. Черновик доступен.';
        this.emit();
        return;
      }
      throw new Error(result.status === 404 ? 'Заметка не найдена или недоступна.' : 'Не удалось загрузить заметку. Повторите попытку.');
    }
    // A save may have completed while this read was in flight. Never regress it.
    if (entry?.saving || (entry && entry.note.revision > result.data.revision)) return;
    if (entry?.dirty) {
      if (entry.note.revision !== result.data.revision) {
        if (entry.note.title === result.data.title && entry.note.content === result.data.content) {
          this.entries.set(id, { note: result.data, dirty: false });
        } else { entry.remote = result.data; entry.conflict = true; entry.error = 'Заметка изменена в другой вкладке. Ваш текст сохранён в черновике.'; }
      }
    } else this.entries.set(id, { note: result.data, dirty: false, editorKey: (entry?.editorKey ?? 0) + (entry && entry.note.content !== result.data.content ? 1 : 0) });
    this.persist();
  }
  async save(id: string) {
    const entry = this.entries.get(id);
    if (!entry?.dirty || entry.saving || entry.conflict || entry.missing) return;
    const sent = { ...entry.note };
    entry.saving = true;
    entry.error = undefined;
    this.emit();
    const result = entry.creating ? await noteApi.create(id, sent.title, sent.content) : await noteApi.save(sent);
    if (result.ok) {
      entry.saving = false;
      entry.creating = false;
      const same = entry.note.title === result.data.title && entry.note.content === result.data.content;
      entry.note = { ...result.data, title: entry.note.title, content: entry.note.content };
      entry.dirty = !same;
      this.persist();
      if (entry.dirty) this.schedule(id);
      return;
    }
    if (result.status === 409) {
      const latest = await noteApi.get(id);
      if (latest.ok && latest.data.title === sent.title && latest.data.content === sent.content) {
        entry.saving = false;
        // The previous save succeeded but its response was lost in transit.
        entry.note = { ...latest.data, title: entry.note.title, content: entry.note.content };
        entry.dirty = entry.note.title !== latest.data.title || entry.note.content !== latest.data.content;
        this.persist();
        if (entry.dirty) this.schedule(id);
        return;
      }
      entry.conflict = true;
      entry.remote = latest.ok ? latest.data : undefined;
      entry.error = 'Заметка изменена в другой вкладке. Сохраните свой текст отдельной копией.';
    } else if (result.status === 404) {
      entry.missing = true;
      entry.error = 'Заметка удалена. Сохраните свой текст отдельной копией.';
    } else {
      entry.error = result.status === 422 ? 'Превышен размер заметки (200 000 символов) или заголовка (300 символов).' : 'Не удалось сохранить. Текст остаётся в черновике.';
      if (result.status === 0 || result.status >= 500) this.schedule(id, 5000);
    }
    entry.saving = false;
    this.persist();
  }
  retryAll = () => {
    for (const [id, entry] of this.entries) if (entry.dirty && !entry.conflict && !entry.missing) this.schedule(id, 100);
  };
  copy(id: string) {
    const entry = this.entries.get(id)!;
    const copyId = this.create(`${entry.note.title || 'Без названия'} — копия`.slice(0, 300), entry.note.content);
    if (entry.remote) this.entries.set(id, { note: entry.remote, dirty: false });
    else this.entries.delete(id);
    this.persist();
    return copyId;
  }
  async remove(id: string) {
    const entry = this.entries.get(id)!;
    if (entry.saving) return false;
    clearTimeout(this.timers.get(id));
    if (entry.creating) {
      // Persist pending creation first so a lost POST response cannot resurrect
      // a supposedly deleted note on the server.
      await this.save(id);
      if (entry.creating || entry.saving || entry.conflict) return false;
    }
    const result = await noteApi.remove(entry.note);
    if (result.ok || result.status === 404) {
      this.entries.delete(id); this.persist(); return true;
    }
    entry.error = result.status === 409 ? 'Заметка изменилась. Обновите её перед удалением.' : 'Не удалось удалить заметку. Повторите попытку.';
    if (result.status === 409) await this.open(id);
    this.emit();
    return false;
  }
}

// A store is scoped by subject, never shared between authenticated users.
const stores = new Map<string, NotesStore>();
export function useNotesStore(owner: string) {
  const store = useMemo(() => {
    let value = stores.get(owner);
    if (!value) { value = new NotesStore(owner); stores.set(owner, value); }
    return value;
  }, [owner]);
  const [, refresh] = useReducer((value) => value + 1, 0);
  useEffect(() => {
    store.listeners.add(refresh);
    store.init();
    store.retryAll();
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if ([...store.entries.values()].some((entry) => entry.dirty)) { event.preventDefault(); }
    };
    window.addEventListener('online', store.retryAll);
    window.addEventListener('beforeunload', beforeUnload);
    return () => {
      store.listeners.delete(refresh);
      window.removeEventListener('online', store.retryAll);
      window.removeEventListener('beforeunload', beforeUnload);
      for (const timer of store.timers.values()) clearTimeout(timer);
      store.timers.clear();
    };
  }, [store]);
  return store;
}
