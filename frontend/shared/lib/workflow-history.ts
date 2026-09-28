import { listWorkflowActivity, listWorkflowAttachmentsPage, listWorkflowCommentsPage, listWorkflowHistory, type UniversityWorkflowStage, type WorkflowActivityApiRecord, type WorkflowAttachmentApiRecord, type WorkflowCommentApiRecord, type WorkflowPage, type WorkflowTransitionApiRecord } from './universities-repository';
import type { WorkflowAttachmentApiRecord as CommentAttachmentRecord } from './workflow-attachments';

export type WorkflowHistoryKind = 'transition' | 'comment' | 'attachment' | 'responsible_changed' | 'deadline_changed';
export const workflowHistoryPresentation: Record<WorkflowHistoryKind, { label: string; icon: WorkflowHistoryKind }> = {
  transition: { label: 'Этап изменён', icon: 'transition' },
  comment: { label: 'Комментарий', icon: 'comment' },
  attachment: { label: 'Файл добавлен', icon: 'attachment' },
  responsible_changed: { label: 'Ответственный изменён', icon: 'responsible_changed' },
  deadline_changed: { label: 'Дедлайн изменён', icon: 'deadline_changed' },
};

export type WorkflowHistoryEvent = {
  id: string;
  stageId?: string | null;
  kind: WorkflowHistoryKind;
  occurredAt: string;
  actorId: string;
  actorName?: string;
  stageName: string;
  title: string;
  text?: string;
  attachments: CommentAttachmentRecord[];
};

async function allPages<T>(load: (page: number) => Promise<WorkflowPage<T>>): Promise<T[]> {
  const first = await load(1);
  const pages = Math.ceil(first.total / first.page_size);
  if (pages <= 1) return first.items;
  const rest = await Promise.all(Array.from({ length: pages - 1 }, (_, index) => load(index + 2)));
  return [first.items, ...rest.map((page) => page.items)].flat();
}

export async function loadWorkflowHistory(instanceId: string): Promise<{ transitions: WorkflowTransitionApiRecord[]; comments: WorkflowCommentApiRecord[]; attachments: WorkflowAttachmentApiRecord[]; activity: WorkflowActivityApiRecord[] }> {
  const [transitions, comments, attachments, activity] = await Promise.all([
    listWorkflowHistory(instanceId),
    allPages((page) => listWorkflowCommentsPage(instanceId, page)),
    allPages((page) => listWorkflowAttachmentsPage(instanceId, page)),
    listWorkflowActivity(instanceId),
  ]);
  return { transitions, comments, attachments, activity };
}

export function buildWorkflowHistory(
  source: Awaited<ReturnType<typeof loadWorkflowHistory>>,
  stages: UniversityWorkflowStage[],
): WorkflowHistoryEvent[] {
  const stageNames = new Map(stages.map((stage) => [stage.templateStageId ?? stage.id, stage.name]));
  const stageName = (id: string | null) => id ? stageNames.get(id) ?? 'Этап Workflow' : 'Весь Workflow';
  const transitions: WorkflowHistoryEvent[] = source.transitions.map((event) => ({
    id: `transition:${event.id}`, stageId: event.to_stage_id, kind: 'transition', occurredAt: event.created_at,
    actorId: event.actor_keycloak_sub, stageName: stageName(event.to_stage_id),
    title: `${event.from_stage_id ? stageName(event.from_stage_id) : 'Создание'} → ${event.to_stage_id ? stageName(event.to_stage_id) : 'Завершение'}`,
    text: event.comment || undefined, attachments: [],
  }));
  const comments: WorkflowHistoryEvent[] = source.comments.map((event) => ({
    id: `comment:${event.id}`, stageId: event.stage_id, kind: 'comment', occurredAt: event.created_at,
    actorId: event.author_keycloak_sub, stageName: stageName(event.stage_id),
    title: workflowHistoryPresentation.comment.label, text: event.content,
    attachments: event.attachments ?? source.attachments.filter((attachment) => attachment.comment_id === event.id),
  }));
  const attachments: WorkflowHistoryEvent[] = source.attachments.filter((event) => !event.comment_id).map((event) => ({
    id: `attachment:${event.id}`, stageId: event.stage_id, kind: 'attachment', occurredAt: event.created_at,
    actorId: event.uploaded_by_keycloak_sub, stageName: stageName(event.stage_id),
    title: workflowHistoryPresentation.attachment.label, attachments: [event],
  }));
  const activity: WorkflowHistoryEvent[] = source.activity.map((event) => ({
    id: `activity:${event.id}`, kind: event.type, occurredAt: event.created_at,
    actorId: '', actorName: event.actor_name, stageName: event.stage_name,
    title: event.title, attachments: [],
  }));
  return [...transitions, ...comments, ...attachments, ...activity].sort((left, right) => left.occurredAt.localeCompare(right.occurredAt) || left.id.localeCompare(right.id));
}

export function buildMockWorkflowHistory(stages: UniversityWorkflowStage[]): WorkflowHistoryEvent[] {
  return stages.flatMap((stage) => stage.transitions.map((event) => ({
    id: `transition:${event.id}`, stageId: stage.id, kind: 'transition' as const,
    occurredAt: event.occurredAt, actorId: '', actorName: event.actor,
    stageName: stage.name,
    title: event.description ?? `${stage.name}: ${event.fromStatus} → ${event.toStatus}`,
    text: event.comment, attachments: [],
  }))).sort((left, right) => left.occurredAt.localeCompare(right.occurredAt) || left.id.localeCompare(right.id));
}
