'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import Trash from '@atomaro/icons/24/action/Trash';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { queryKeys } from '@/shared/lib/query-keys';
import { archiveWorkflowInstance, isRealWorkflowMode } from '@/shared/lib/universities-repository';
import { universityWorkflowInstancesQueryKey } from '@/shared/lib/workflow-creation-repository';
import { Button } from '@/shared/ui/rtk/button';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Modal } from '@/shared/ui/rtk/modal';

export function WorkflowArchiveAction({ instanceId, universityId, active, label = 'Архивировать Workflow' }: { instanceId: string; universityId: string; active: boolean; label?: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const archive = useMutation({
    mutationFn: () => archiveWorkflowInstance(instanceId),
    onSuccess: async () => {
      setOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowOverview }),
        queryClient.invalidateQueries({ queryKey: universityWorkflowInstancesQueryKey(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowByProgramFamily(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.passport(universityId) }),
        queryClient.invalidateQueries({ queryKey: ['workflow', 'instances'] }),
      ]);
    },
    onError: (cause) => setError(normalizeApiError(cause).message),
  });
  if (!active || !isRealWorkflowMode() || !hasPermission(user, 'workflow.change_status')) return null;
  return <>
    <IconButton icon={<Trash size={18} fill="currentColor" />} label={label} size={18} intent="danger" onClick={() => { setError(null); setOpen(true); }} />
    {open ? <Modal title="Архивировать Workflow?" onClose={() => { if (!archive.isPending) setOpen(false); }}><p>Процесс исчезнет из активных списков. История, комментарии и файлы сохранятся.</p>{error ? <p role="alert">{error}</p> : null}<div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}><Button type="button" variant="ghost" size="s" disabled={archive.isPending} onClick={() => setOpen(false)}>Отмена</Button><Button type="button" variant="danger" size="s" loading={archive.isPending} onClick={() => archive.mutate()}>Архивировать</Button></div></Modal> : null}
  </>;
}
