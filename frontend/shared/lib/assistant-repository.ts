import { apiFetch, type ApiResult } from './api-client';

export interface AssistantSource {
  id: string;
  title: string;
  url: string;
  excerpt: string;
}

export interface AssistantTurn {
  conversation_id: string;
  turn_id: string;
  revision: number;
  question: string;
  answer: string;
  sources: AssistantSource[];
  created_at: string;
}

export type AssistantChatReply = Omit<AssistantTurn, 'question'>;

interface Conversation {
  id: string;
  revision: number;
}

interface ConversationPage {
  items: Conversation[];
  total: number;
}

interface TurnPage {
  conversation: Conversation;
  items: AssistantTurn[];
  total: number;
}

export type AssistantPage = 'dashboard' | 'universities' | 'university' | 'workflows' | 'workflow' | 'reports' | 'audit' | 'catalogs' | 'import' | 'users' | 'workflow_templates' | 'docs';

export function assistantPage(pathname: string): AssistantPage | undefined {
  if (pathname === '/dashboard') return 'dashboard';
  if (pathname === '/universities') return 'universities';
  if (pathname.startsWith('/universities/')) return 'university';
  if (pathname === '/workflows') return 'workflows';
  if (pathname.startsWith('/workflows/')) return 'workflow';
  if (pathname === '/reports') return 'reports';
  if (pathname === '/audit') return 'audit';
  if (pathname.startsWith('/admin/catalogs')) return 'catalogs';
  if (pathname.startsWith('/admin/import')) return 'import';
  if (pathname.startsWith('/admin/users')) return 'users';
  if (pathname.startsWith('/admin/workflow/templates')) return 'workflow_templates';
  if (pathname.startsWith('/docs')) return 'docs';
  return undefined;
}

const base = '/api/v1/assistant';

export const assistantRepository = {
  latestConversation: (): Promise<ApiResult<ConversationPage>> =>
    apiFetch(`${base}/conversations?page=1&page_size=1`),
  history: (id: string, page: number): Promise<ApiResult<TurnPage>> =>
    apiFetch(`${base}/conversations/${encodeURIComponent(id)}?page=${page}&page_size=50`),
  chat: (message: string, page: AssistantPage | undefined, conversationId: string | null, revision: number | null): Promise<ApiResult<AssistantChatReply>> =>
    apiFetch(`${base}/chat`, {
      method: 'POST',
      body: {
        message,
        ...(page ? { page } : {}),
        ...(conversationId ? { conversation_id: conversationId, expected_revision: revision } : {}),
      },
    }),
};
