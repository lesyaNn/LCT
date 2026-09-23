import type { UniversityWorkflowStage } from './universities-repository';

export const WORKFLOW_TRANSITION_DRAFT_VERSION = 1;

export interface WorkflowTransitionTarget {
  id: string;
  orderIndex: number;
  name: string;
}

export interface WorkflowTransitionDraft {
  version: typeof WORKFLOW_TRANSITION_DRAFT_VERSION;
  comment: string;
  dueDate: string;
  targetStageId: string;
  updatedAt: string;
}

export function getAvailableWorkflowTransitionTargets(stages: UniversityWorkflowStage[], currentStage: UniversityWorkflowStage): WorkflowTransitionTarget[] {
  const ordered = stages.slice().sort((left, right) => left.orderIndex - right.orderIndex);
  return ordered
    .filter((target) => target.orderIndex > currentStage.orderIndex)
    .filter((target) => target.status !== 'completed' && target.status !== 'skipped')
    .filter((target) => ordered.filter((stage) => stage.orderIndex > currentStage.orderIndex && stage.orderIndex < target.orderIndex).every((stage) => stage.isOptional === true))
    .map((target) => ({ id: target.id, orderIndex: target.orderIndex, name: target.name }));
}

export function workflowTransitionDraftKey(instanceId: string, currentStageId: string, userId?: string | null): string {
  const owner = userId || 'anonymous';
  return `workflow.transition.draft.v${WORKFLOW_TRANSITION_DRAFT_VERSION}:${instanceId}:${currentStageId}:${owner}`;
}

export function isWorkflowTransitionDraft(value: unknown, targetIds: Set<string>): value is WorkflowTransitionDraft {
  if (!value || typeof value !== 'object') return false;
  const draft = value as Partial<WorkflowTransitionDraft>;
  return draft.version === WORKFLOW_TRANSITION_DRAFT_VERSION
    && typeof draft.comment === 'string'
    && draft.comment.length <= 5000
    && typeof draft.dueDate === 'string'
    && (draft.dueDate === '' || /^\d{4}-\d{2}-\d{2}$/.test(draft.dueDate))
    && typeof draft.targetStageId === 'string'
    && targetIds.has(draft.targetStageId)
    && typeof draft.updatedAt === 'string';
}

export function getLocalTodayIso(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}
