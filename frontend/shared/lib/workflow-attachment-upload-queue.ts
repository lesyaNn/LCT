'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { uploadWorkflowAttachment, validateWorkflowUploadFile, type WorkflowAttachmentApiRecord } from './workflow-attachments';

export const WORKFLOW_UPLOAD_MAX_CONCURRENCY = 3;

export type WorkflowUploadStatus = 'queued' | 'uploading' | 'processing' | 'success' | 'error' | 'cancelled';

export interface WorkflowUploadQueueItem {
  id: string;
  file: File;
  status: WorkflowUploadStatus;
  progress: number;
  error?: string;
  validationError?: boolean;
  serverAttachmentId?: string;
}

function createQueueId(): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `upload:${random}`;
}

export function useAttachmentUploadQueue({ instanceId, onSuccess, onServerError }: { instanceId: string; onSuccess: (attachment: WorkflowAttachmentApiRecord) => void; onServerError?: (message: string) => void }) {
  const [items, setItems] = useState<WorkflowUploadQueueItem[]>([]);
  const controllers = useRef(new Map<string, AbortController>());
  const removalTimers = useRef(new Map<string, number>());
  const mounted = useRef(true);

  const removeItem = useCallback((id: string) => {
    const controller = controllers.current.get(id);
    if (controller) controller.abort();
    controllers.current.delete(id);
    const timer = removalTimers.current.get(id);
    if (timer) window.clearTimeout(timer);
    removalTimers.current.delete(id);
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const removeAfter = useCallback((id: string, delay: number, beforeRemove?: () => void) => {
    const previousTimer = removalTimers.current.get(id);
    if (previousTimer) window.clearTimeout(previousTimer);
    const timer = window.setTimeout(() => {
      removalTimers.current.delete(id);
      if (!mounted.current) return;
      beforeRemove?.();
      setItems((current) => current.filter((item) => item.id !== id));
    }, delay);
    removalTimers.current.set(id, timer);
  }, []);

  const startUpload = useCallback((item: WorkflowUploadQueueItem) => {
    if (controllers.current.has(item.id)) return;
    const controller = new AbortController();
    controllers.current.set(item.id, controller);
    setItems((current) => current.map((candidate) => candidate.id === item.id && candidate.status === 'queued' ? { ...candidate, status: 'uploading', progress: 0, error: undefined } : candidate));

    void uploadWorkflowAttachment(instanceId, item.file, {
      signal: controller.signal,
      onProgress: (progress) => {
        if (!mounted.current || controller.signal.aborted) return;
        setItems((current) => current.map((candidate) => candidate.id === item.id && (candidate.status === 'uploading' || candidate.status === 'processing')
          ? { ...candidate, status: progress >= 100 ? 'processing' : 'uploading', progress }
          : candidate));
      },
    }).then((attachment) => {
      // A resolved request is authoritative even if the user clicked cancel at
      // the same instant as the response arrived: the backend already stored it.
      if (!mounted.current) return;
      setItems((current) => current.map((candidate) => candidate.id === item.id ? { ...candidate, status: 'success', progress: 100, serverAttachmentId: attachment.id } : candidate));
      onSuccess(attachment);
      removeAfter(item.id, 700);
    }).catch((cause: unknown) => {
      if (!mounted.current || controller.signal.aborted || (cause instanceof DOMException && cause.name === 'AbortError')) return;
      const message = cause instanceof Error ? cause.message : 'Не удалось загрузить файл.';
      setItems((current) => current.map((candidate) => candidate.id === item.id ? { ...candidate, status: 'error', error: message, progress: 0, validationError: false, serverAttachmentId: undefined } : candidate));
      onServerError?.(message);
    }).finally(() => {
      controllers.current.delete(item.id);
    });
  }, [instanceId, onServerError, onSuccess, removeAfter]);

  useEffect(() => {
    const activeCount = items.filter((item) => item.status === 'uploading' || item.status === 'processing').length;
    const available = Math.max(0, WORKFLOW_UPLOAD_MAX_CONCURRENCY - activeCount);
    if (!available) return;
    items.filter((item) => item.status === 'queued').slice(0, available).forEach(startUpload);
  }, [items, startUpload]);

  useEffect(() => {
    mounted.current = true;
    const uploadControllers = controllers.current;
    const pendingRemovalTimers = removalTimers.current;
    return () => {
      mounted.current = false;
      uploadControllers.forEach((controller) => controller.abort());
      uploadControllers.clear();
      pendingRemovalTimers.forEach((timer) => window.clearTimeout(timer));
      pendingRemovalTimers.clear();
    };
  }, []);

  const addFiles = useCallback((files: File[]) => {
    const added = files.map((file): WorkflowUploadQueueItem => {
      const validation = validateWorkflowUploadFile(file);
      return validation.valid
        ? { id: createQueueId(), file, status: 'queued', progress: 0 }
        : { id: createQueueId(), file, status: 'error', progress: 0, error: validation.message, validationError: true };
    });
    if (added.length) setItems((current) => [...current, ...added]);
  }, []);

  const cancel = useCallback((id: string) => {
    controllers.current.get(id)?.abort();
    controllers.current.delete(id);
    setItems((current) => current.map((item) => item.id === id ? { ...item, status: 'cancelled', progress: 0, error: undefined, serverAttachmentId: undefined } : item));
    removeAfter(id, 700);
  }, [removeAfter]);

  const retry = useCallback((id: string) => {
    setItems((current) => current.map((item) => item.id === id && item.status === 'error' && !item.validationError ? { ...item, status: 'queued', progress: 0, error: undefined, serverAttachmentId: undefined } : item));
  }, []);

  return { items, addFiles, cancel, retry, remove: removeItem };
}
