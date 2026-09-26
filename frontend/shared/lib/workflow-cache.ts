import type { QueryClient } from '@tanstack/react-query';
import { queryKeys } from './query-keys';
import { dashboardQueryKey } from './dashboard-repository';
import {
  universityHistoryFamilyQueryKey,
  universityPassportQueryKey,
  universitiesQueryKey,
  workflowQueryKey,
  type UniversityWorkflow,
  type UniversityWorkflowAttachment,
} from './universities-repository';

export function invalidateWorkflowDetail(queryClient: QueryClient, instanceId: string): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) });
}

function patchWorkflowStageAttachments(queryClient: QueryClient, instanceId: string, stageId: string, update: (attachments: UniversityWorkflowAttachment[]) => UniversityWorkflowAttachment[]): void {
  queryClient.setQueryData<UniversityWorkflow>(workflowQueryKey(instanceId), (current) => {
    if (!current) return current;
    const stages = current.stages.map((stage) => stage.id === stageId ? { ...stage, attachments: update(stage.attachments) } : stage);
    return { ...current, stages, currentStage: current.currentStage ? stages.find((stage) => stage.id === current.currentStage?.id) ?? current.currentStage : null };
  });
}

export function addWorkflowAttachmentToCache(queryClient: QueryClient, instanceId: string, stageId: string, attachment: UniversityWorkflowAttachment): void {
  patchWorkflowStageAttachments(queryClient, instanceId, stageId, (attachments) => attachments.some((item) => item.id === attachment.id) ? attachments : [...attachments, attachment]);
}

export function removeWorkflowAttachmentFromCache(queryClient: QueryClient, instanceId: string, stageId: string, attachmentId: string): void {
  patchWorkflowStageAttachments(queryClient, instanceId, stageId, (attachments) => attachments.filter((attachment) => attachment.id !== attachmentId));
}

/**
 * Mark only the server-state representations affected by a workflow transition
 * as stale. Query families are addressed by their existing prefixes, so every
 * filter/sort/page variant of the universities list is covered without touching
 * unrelated application cache entries.
 */
export function invalidateWorkflowRelatedQueries(queryClient: QueryClient, instanceId: string, universityId?: string | null): Promise<unknown[]> {
  const invalidations = [
    invalidateWorkflowDetail(queryClient, instanceId),
    queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowOverview }),
    queryClient.invalidateQueries({ queryKey: universitiesQueryKey }),
    queryClient.invalidateQueries({ queryKey: dashboardQueryKey }),
    queryClient.invalidateQueries({ queryKey: queryKeys.audit.all }),
  ];

  if (universityId) {
    invalidations.push(
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowByProgramFamily(universityId) }),
      queryClient.invalidateQueries({ queryKey: universityPassportQueryKey(universityId) }),
      queryClient.invalidateQueries({ queryKey: universityHistoryFamilyQueryKey(universityId) }),
    );
  }

  return Promise.all(invalidations);
}
