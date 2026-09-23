import type { AuthUser } from '@/shared/types/user';
import type { UniversityWorkflowComment } from './universities-repository';

export const WORKFLOW_COMMENT_EDIT_WINDOW_MS = 15 * 60 * 1000;

export function canEditWorkflowComment(comment: UniversityWorkflowComment, user: AuthUser | null, now = Date.now()): boolean {
  if (!user || comment.isSystem) return false;
  if (user.role === 'admin') return true;
  if (!comment.authorId || comment.authorId !== user.id) return false;
  const createdAt = Date.parse(comment.occurredAt);
  return Number.isFinite(createdAt) && now - createdAt <= WORKFLOW_COMMENT_EDIT_WINDOW_MS;
}

export function canDeleteWorkflowComment(comment: UniversityWorkflowComment, user: AuthUser | null): boolean {
  return Boolean(user && !comment.isSystem && (user.role === 'admin' || comment.authorId === user.id) && comment.canDelete);
}
