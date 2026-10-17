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
  const messages: Record<string, string> = {
    ASSISTANT_DISABLED: 'ИИ-помощник сейчас выключен.',
    ASSISTANT_UNAVAILABLE: 'Модель помощника сейчас недоступна. Попробуйте позже.',
    ASSISTANT_KNOWLEDGE_UNAVAILABLE: 'Инструкции помощника сейчас недоступны.',
    ASSISTANT_STORAGE_UNAVAILABLE: 'Не удалось сохранить диалог. Попробуйте позже.',
    ASSISTANT_TIMEOUT: 'Помощник не успел ответить. Попробуйте ещё раз.',
    ASSISTANT_BUSY: 'Помощник занят. Попробуйте через несколько секунд.',
    ASSISTANT_INVALID_RESPONSE: 'Помощник не смог сформировать ответ. Попробуйте ещё раз.',
    RATE_LIMITED: 'Слишком много вопросов. Попробуйте немного позже.',
    CONFLICT: 'История диалога изменилась. Нажмите «Повторить», чтобы отправить вопрос снова.',
  };
  return (error.code && messages[error.code]) || error.message;
}

export function useAssistantChat(userId: string, pathname: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [revision, setRevision] = useState<number | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [restoreError, setRestoreError] = useState('');
  const [sending, setSending] = useState(false);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const sendingRef = useRef(false);

  useEffect(() => {
    let active = true;
    async function restore() {
      let latest;
      try { latest = await assistantRepository.latestConversation(); }
      catch {
        if (active) { setRestoreError('Не удалось связаться с сервером.'); setRestoring(false); }
        return;
      }
      if (!active) return;
      if (!latest.ok) {
        setRestoreError(assistantError(latest));
        setRestoring(false);
        return;
      }
      const conversation = latest.data.items[0];
      if (!conversation) {
        setMessages([]);
        setConversationId(null);
        setRevision(null);
        setRestoreError('');
        setRestoring(false);
        return;
      }
      const turns: AssistantTurn[] = [];
      let page = 1;
      let total = 0;
      do {
        let result;
        try { result = await assistantRepository.history(conversation.id, page); }
        catch {
          if (active) { setRestoreError('Не удалось связаться с сервером.'); setRestoring(false); }
          return;
        }
        if (!active) return;
        if (!result.ok) {
          setRestoreError(assistantError(result));
          setRestoring(false);
          return;
        }
        turns.push(...result.data.items);
        total = result.data.total;
        setRevision(result.data.conversation.revision);
        page += 1;
      } while (turns.length < total);
      setMessages(restoredMessages(turns));
      setConversationId(conversation.id);
      setRestoreError('');
      setRestoring(false);
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
      try {
        let currentId = conversationId;
        let currentRevision = revision;
        if (retryId && currentId) {
          const refreshed = await assistantRepository.history(currentId, 1);
          if (refreshed.ok) currentRevision = refreshed.data.conversation.revision;
          else if (refreshed.status === 404) { currentId = null; currentRevision = null; }
          else {
            setMessages((current) => current.map((item) => item.id === localId ? { ...item, error: assistantError(refreshed) } : item));
            return;
          }
        }
        const result = await assistantRepository.chat(question, assistantPage(pathname), currentId, currentRevision);
        if (!result.ok) {
          setMessages((current) => current.map((item) => item.id === localId ? { ...item, error: assistantError(result) } : item));
          return;
        }
        if (!result.data?.answer?.trim()) {
          setMessages((current) => current.map((item) => item.id === localId ? { ...item, error: 'Помощник вернул пустой ответ. Попробуйте ещё раз.' } : item));
          return;
        }
        setConversationId(result.data.conversation_id);
        setRevision(result.data.revision);
        setRestoreError('');
        setMessages((current) => [...current, {
          id: result.data.turn_id,
          role: 'assistant',
          text: result.data.answer,
          createdAt: result.data.created_at,
          sources: result.data.sources,
        }]);
      } catch {
        setMessages((current) => current.map((item) => item.id === localId ? { ...item, error: 'Не удалось связаться с сервером. Попробуйте ещё раз.' } : item));
      } finally {
        sendingRef.current = false;
        setSending(false);
      }
    })();
    return true;
  }, [conversationId, pathname, restoring, revision]);

  return {
    messages, sending, restoring, restoreError, sendMessage,
    retry: (message: ChatMessage) => sendMessage(message.text, message.id),
    retryRestore: () => { setRestoring(true); setRestoreAttempt((value) => value + 1); },
  };
}
