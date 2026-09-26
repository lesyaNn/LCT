import type { UniversityWorkflow, UniversityWorkflowStage } from './universities-repository';

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

export function getAvailableWorkflowRollbackTargets(stages: UniversityWorkflowStage[], currentStage: UniversityWorkflowStage): WorkflowTransitionTarget[] {
  return stages
    .filter((target) => target.orderIndex < currentStage.orderIndex)
    .filter((target) => target.status === 'completed' || target.status === 'skipped')
    .sort((left, right) => right.orderIndex - left.orderIndex)
    .map((target) => ({ id: target.id, orderIndex: target.orderIndex, name: target.name }));
}

/**
 * Apply the visual part of a rollback to a cached workflow snapshot.
 * Mirrors the server policy: the target and every stage between it and the
 * current one reopen (pending), the pointer moves back to the target.
 */
export function applyOptimisticWorkflowRollback(workflow: UniversityWorkflow, targetStageId: string): UniversityWorkflow {
  const currentStage = workflow.stages.find((stage) => stage.status === 'current') ?? workflow.currentStage;
  const targetStage = workflow.stages.find((stage) => stage.id === targetStageId);
  if (!currentStage || !targetStage || targetStage.orderIndex >= currentStage.orderIndex) return workflow;

  const stages = workflow.stages.map((stage) => {
    if (stage.id === targetStage.id) return { ...stage, status: 'current' as const, startedAt: new Date().toISOString(), completedAt: null, completion: null };
    if (stage.orderIndex >= targetStage.orderIndex && stage.orderIndex < currentStage.orderIndex) {
      return { ...stage, status: 'pending' as const, completedAt: null, completion: null };
    }
    if (stage.id === currentStage.id) return { ...stage, status: 'pending' as const, completedAt: null, completion: null };
    return stage;
  });

  return {
    ...workflow,
    currentStage: stages.find((stage) => stage.id === targetStage.id) ?? targetStage,
    completedSteps: stages.filter((stage) => stage.status === 'completed' || stage.status === 'skipped').length,
    stages,
  };
}
/**
 * Apply the visual part of a forward transition to a cached workflow snapshot.
 * The server remains authoritative; this helper only supplies the immediate UI
 * state and is paired with a mutation snapshot for exact rollback.
 */
export function applyOptimisticWorkflowTransition(workflow: UniversityWorkflow, targetStageId: string, occurredAt = new Date().toISOString()): UniversityWorkflow {
  const currentStage = workflow.stages.find((stage) => stage.status === 'current') ?? workflow.currentStage;
  const targetStage = workflow.stages.find((stage) => stage.id === targetStageId);
  if (!currentStage || !targetStage || targetStage.orderIndex <= currentStage.orderIndex) return workflow;
  const completion = currentStage.deadline && occurredAt.slice(0, 10) > currentStage.deadline ? 'late' as const : 'on_time' as const;

  const stages = workflow.stages.map((stage) => {
    if (stage.id === currentStage.id) return { ...stage, status: 'completed' as const, completedAt: occurredAt, completion };
    if (stage.id === targetStage.id) return { ...stage, status: 'current' as const, startedAt: occurredAt, completedAt: null, completion: null };
    if (stage.orderIndex > currentStage.orderIndex && stage.orderIndex < targetStage.orderIndex && stage.isOptional) {
      return { ...stage, status: 'skipped' as const, completedAt: occurredAt, completion: 'on_time' as const };
    }
    return stage;
  });

  return {
    ...workflow,
    currentStage: stages.find((stage) => stage.id === targetStage.id) ?? targetStage,
    completedSteps: stages.filter((stage) => stage.status === 'completed' || stage.status === 'skipped').length,
    stages,
  };
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
