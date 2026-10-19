'use client';

import type { JSONContent } from '@tiptap/core';
import { apiDownload, apiFetch } from './api-client';

export type Note = { id: string; title: string; content: string; revision: number; created_at: string; updated_at: string };
export type NoteSummary = Omit<Note, 'content'> & { snippet: string };
export type NotePage = { items: NoteSummary[]; total: number };
export type Mention = { kind: 'user' | 'university' | 'direction' | 'program' | 'vendor' | 'workflow' | 'document' | 'contract' | 'license' | 'product' | 'responsible'; id: string; title: string; subtitle: string; href: string | null; university_id: string | null };
export type MentionKind = Mention['kind'] | 'agreements';
export const noteApi = {
  initialize: () => apiFetch<void>('/api/v1/notes/initialize', { method: 'POST' }),
  exportPdf: (title: string, document: JSONContent, signal?: AbortSignal) => apiDownload('/api/v1/notes/export/pdf', signal, { method: 'POST', body: { title, document } }),
  list: (params: URLSearchParams, signal?: AbortSignal) => apiFetch<NotePage>(`/api/v1/notes?${params}`, { signal }),
  get: (id: string) => apiFetch<Note>(`/api/v1/notes/${encodeURIComponent(id)}`),
  create: (id: string, title = '', content = '') => apiFetch<Note>('/api/v1/notes', { method: 'POST', body: { id, title, content } }),
  save: (note: Note) => apiFetch<Note>(`/api/v1/notes/${note.id}`, { method: 'PATCH', body: { title: note.title, content: note.content, revision: note.revision } }),
  remove: (note: Note) => apiFetch<void>(`/api/v1/notes/${note.id}?revision=${note.revision}`, { method: 'DELETE' }),
  mentions: (kind: MentionKind, q: string, signal?: AbortSignal) => apiFetch<Mention[]>(`/api/v1/notes/mentions?${new URLSearchParams({ kind, q })}`, { signal }),
  resolve: (params: string) => apiFetch<Mention[]>(`/api/v1/notes/mentions?${params}`),
};

export function mentionHref(mention: Mention): string {
  return `/notes/reference?${new URLSearchParams({ kind: mention.kind, target_id: mention.id, ...(mention.university_id ? { university_id: mention.university_id } : {}) })}`;
}

export function markdownLabel(label: string): string {
  return label.replace(/[\\[\]`*_~]/g, '\\$&').replace(/\s+/g, ' ');
}
