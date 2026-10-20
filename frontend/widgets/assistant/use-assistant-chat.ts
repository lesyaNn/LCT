'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { assistantPage, assistantRepository, type AssistantSource, type AssistantTurn } from '@/shared/lib/assistant-repository';
import type { ApiResult } from '@/shared/lib/api-client';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  createdAt: string;
  sources?: AssistantSource[];
  error?: string;
}

function restoredMessages(turns: AssistantTurn[]): ChatMessage[] {
  return turns.flatMap((turn) => [
    { id: `${turn.turn_id}:question`, role: 'user' as const, text: turn.question, createdAt: turn.created_at },
    ...(turn.answer?.trim() ? [{ id: `${turn.turn_id}:answer`, role: 'assistant' as const, text: turn.answer, createdAt: turn.created_at, sources: turn.sources }] : []),
  ]);
}

function assistantError(result: Extract<ApiResult<unknown>, { ok: false }>): string {
  const error = normalizeApiError({ status: result.status, body: result.body, message: result.error }, { fallbackMessage: 'Помощник не смог ответить. Попробуйте позже.' });
  if (error.code === 'CONFLICT' && error.details.reason === 'turn_limit') return 'В этом диалоге достигнут лимит сообщений. Нажмите Новый диалог, чтобы продолжить.';
  const messages: Record<string, string> = {
    ASSISTANT_DISABLED: 'ИИ-помощник сейчас выключен.',
    ASSISTANT_UNAVAILABLE: 'Модель помощника сейчас недоступна. Попробуйте позже.',
    ASSISTANT_KNOWLEDGE_UNAVAILABLE: 'Инструкции помощника сейчас недоступны.',
    ASSISTANT_STORAGE_UNAVAILABLE: 'Не удалось сохранить диалог. Попробуйте позже.',
    ASSISTANT_TIMEOUT: 'Помощник не успел ответить. Попробуйте ещё раз.',
    ASSISTANT_BUSY: 'Помощник занят. Попробуйте через несколько секунд.',
    ASSISTANT_INVALID_RESPONSE: 'Помощник не смог сформировать ответ. Попробуйте ещё раз.',
    RATE_LIMITED: 'Слишком много вопросов. Попробуйте немного позже.',
    CONFLICT: 'История диалога снова изменилась. Нажмите Повторить, чтобы отправить вопрос с актуальной версией.',
  };
  return (error.code && messages[error.code]) || error.message;
}

interface HistoryData { turns: AssistantTurn[]; revision: number }

async function readHistory(id: string): Promise<ApiResult<HistoryData>> {
  const turns: AssistantTurn[] = [];
  let revision: number | null = null;
  // The server caps a conversation at 500 turns. Bound malformed pagination too.
  for (let page = 1; page <= 20; page += 1) {
    const result = await assistantRepository.history(id, page);
    if (!result.ok) return result;
    if (revision !== null && revision !== result.data.conversation.revision) {
      return { ok: false, status: 409, error: 'History changed', body: { error: { code: 'CONFLICT', details: { field: 'revision' } } } };
    }
    revision = result.data.conversation.revision;
    turns.push(...result.data.items);
    if (turns.length >= result.data.total) return { ok: true, status: 200, data: { turns, revision } };
    if (!result.data.items.length) break;
  }
  return { ok: false, status: 502, error: 'Incomplete conversation history' };
}

export function useAssistantChat(userId: string, pathname: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const context = useRef<{ id: string | null; revision: number | null }>({ id: null, revision: null });
  const [restoring, setRestoring] = useState(true);
  const [restoreError, setRestoreError] = useState('');
  const [sending, setSending] = useState(false);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const sendingRef = useRef(false);

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        const latest = await assistantRepository.latestConversation();
        if (!active) return;
        if (!latest.ok) { setRestoreError(assistantError(latest)); return; }
        const conversation = latest.data.items[0];
        if (!conversation) {
          setMessages([]);
          context.current = { id: null, revision: null };
          setRestoreError('');
          return;
        }
        const history = await readHistory(conversation.id);
        if (!active) return;
        if (!history.ok) { setRestoreError(assistantError(history)); return; }
        setMessages(restoredMessages(history.data.turns));
        context.current = { id: conversation.id, revision: history.data.revision };
        setRestoreError('');
      } catch {
        if (active) setRestoreError('Не удалось связаться с сервером.');
      } finally {
        if (active) setRestoring(false);
      }
    }
    void restore();
    return () => { active = false; };
  }, [userId, restoreAttempt]);

  const sendMessage = useCallback((rawQuestion: string, retryId?: string): boolean => {
    const question = rawQuestion.trim();
    if (!question || question.length > 2000 || restoring || sendingRef.current) return false;
    sendingRef.current = true;
    setSending(true);
    const localId = retryId ?? `local:${crypto.randomUUID()}`;
    if (retryId) setMessages((current) => current.map((item) => item.id === retryId ? { ...item, error: undefined } : item));
    else setMessages((current) => [...current, { id: localId, role: 'user', text: question, createdAt: new Date().toISOString() }]);

    void (async () => {
      const fail = (error: string) => setMessages((current) => current.map((item) => item.id === localId ? { ...item, error } : item));
      async function synchronize(): Promise<boolean> {
        const id = context.current.id;
        if (!id) return true;
        const refreshed = await readHistory(id);
        if (!refreshed.ok) {
          if (refreshed.status === 404) {
            context.current = { id: null, revision: null };
            setMessages((current) => current.filter((item) => item.id.startsWith('local:')));
            return true;
          }
          fail(assistantError(refreshed));
          return false;
        }
        // Keep this version even if the following model request fails.
        context.current = { id, revision: refreshed.data.revision };
        setMessages((current) => [...restoredMessages(refreshed.data.turns), ...current.filter((item) => item.id.startsWith('local:'))]);
        return true;
      }
      const post = () => assistantRepository.chat(question, assistantPage(pathname), context.current.id, context.current.revision);
      try {
        if (!await synchronize()) return;
        let result = await post();
        if (!result.ok && result.status === 409) {
          const conflict = normalizeApiError({ status: result.status, body: result.body });
          // Only an explicit rejected revision is safe to retry automatically.
          // Never repeat an uncertain network/5xx result or a turn-limit error.
          if (conflict.details.field === 'revision' && await synchronize()) result = await post();
        }
        if (!result.ok) { fail(assistantError(result)); return; }
        if (!result.data?.answer?.trim()) { fail('Помощник вернул пустой ответ. Попробуйте ещё раз.'); return; }
        const reply = result.data;
        context.current = { id: reply.conversation_id, revision: reply.revision };
        setRestoreError('');
        setMessages((current) => [...current.map((item) => item.id === localId ? { ...item, id: `${reply.turn_id}:question`, error: undefined } : item), {
          id: `${reply.turn_id}:answer`, role: 'assistant', text: reply.answer, createdAt: reply.created_at, sources: reply.sources,
        }]);
      } catch {
        fail('Не удалось связаться с сервером. Попробуйте ещё раз.');
      } finally {
        sendingRef.current = false;
        setSending(false);
      }
    })();
    return true;
  }, [pathname, restoring]);

  return {
    messages, sending, restoring, restoreError, sendMessage,
    retry: (message: ChatMessage) => sendMessage(message.text, message.id),
    retryRestore: () => { if (!sendingRef.current) { setRestoring(true); setRestoreAttempt((value) => value + 1); } },
    startNew: () => {
      if (sendingRef.current || restoring) return false;
      context.current = { id: null, revision: null };
      setMessages([]);
      setRestoreError('');
      return true;
    },
  };
}
