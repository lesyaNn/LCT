import type { AuthUser } from '@/shared/types/user';
import type { UniversityWorkflowAttachment } from './universities-repository';

export type WorkflowAttachmentCategory = 'pdf' | 'image' | 'archive' | 'document' | 'spreadsheet' | 'other';

export function getWorkflowAttachmentCategory(mimeType?: string, fileName = ''): WorkflowAttachmentCategory {
  const mime = mimeType?.toLowerCase() ?? '';
  const extension = fileName.split('.').pop()?.toLowerCase() ?? '';
  if (mime === 'application/pdf' || extension === 'pdf') return 'pdf';
  if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(extension)) return 'image';
  if (mime.includes('zip') || mime.includes('compressed') || ['zip', 'rar', '7z', 'tar', 'gz'].includes(extension)) return 'archive';
  if (mime.includes('spreadsheet') || mime.includes('excel') || ['xls', 'xlsx', 'csv', 'ods'].includes(extension)) return 'spreadsheet';
  if (mime.startsWith('text/') || mime.includes('word') || mime.includes('document') || ['doc', 'docx', 'txt', 'rtf', 'odt'].includes(extension)) return 'document';
  return 'other';
}

export function isWorkflowImageAttachment(mimeType?: string, fileName = ''): boolean {
  return getWorkflowAttachmentCategory(mimeType, fileName) === 'image';
}

export function canDeleteWorkflowAttachment(attachment: UniversityWorkflowAttachment, user: AuthUser | null): boolean {
  return Boolean(user && attachment.canDelete && (user.role === 'admin' || user.role === 'manager'));
}
