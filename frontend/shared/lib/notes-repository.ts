import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';

export type NoteView = 'all' | 'pinned' | 'recent' | 'trash';
export type NoteSort = 'updated' | 'title';
export type NoteFolder = { id: string; name: string };
export type NoteSummary = {
  id: string; title: string; excerpt: string; folder_id: string | null;
  pinned: boolean; revision: number; updated_at: string; deleted_at: string | null;
};
export type Note = Omit<NoteSummary, 'excerpt'> & { content: string; created_at: string };
export type NoteList = { items: NoteSummary[]; total: number; page: number; page_size: number };
export type NoteLinkOption = { kind: string; title: string; subtitle: string | null; href: string };
export type ResolvedNoteLink = { href: string; title: string | null; available: boolean };

async function notesRequest<T>(path: string, method: 'GET' | 'POST' | 'PATCH' | 'DELETE' = 'GET', body?: unknown): Promise<T> {
  const result = await apiFetch<T>(`/api/v1/notes${path}`, { method, body });
  if (!result.ok) throw new ApiRequestError(result.status, result.body, result.error);
  return result.data;
}

export const notesApi = {
  list: (params: { view: NoteView; q: string; folderId: string | null; sort: NoteSort; page: number }) => {
    const query = new URLSearchParams({ view: params.view, q: params.q, sort: params.sort, page: String(params.page) });
    if (params.folderId) query.set('folder_id', params.folderId);
    return notesRequest<NoteList>(`?${query}`);
  },
  get: (id: string) => notesRequest<Note>(`/${id}`),
  create: (body: { title?: string; content?: string; folder_id?: string | null }) => notesRequest<Note>('', 'POST', body),
  update: (id: string, body: { revision: number; title?: string; content?: string; folder_id?: string | null; pinned?: boolean }) => notesRequest<Note>(`/${id}`, 'PATCH', body),
  remove: (id: string) => notesRequest<void>(`/${id}`, 'DELETE'),
  restore: (id: string) => notesRequest<Note>(`/${id}/restore`, 'POST'),
  purge: (id: string) => notesRequest<void>(`/${id}/permanent`, 'DELETE'),
  folders: () => notesRequest<NoteFolder[]>('/folders'),
  createFolder: (name: string) => notesRequest<NoteFolder>('/folders', 'POST', { name }),
  renameFolder: (id: string, name: string) => notesRequest<NoteFolder>(`/folders/${id}`, 'PATCH', { name }),
  deleteFolder: (id: string) => notesRequest<void>(`/folders/${id}`, 'DELETE'),
  linkOptions: (q: string) => notesRequest<NoteLinkOption[]>(`/link-options?q=${encodeURIComponent(q)}`),
  resolveLinks: (hrefs: string[]) => notesRequest<ResolvedNoteLink[]>('/resolve-links', 'POST', { hrefs }),
};
