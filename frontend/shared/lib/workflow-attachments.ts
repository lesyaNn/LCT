import type { AuthUser } from '@/shared/types/user';
import { hasPermission, hasRole } from './access-control';
import { apiUploadFormData } from './api-client';
import { ApiRequestError, ERROR_MESSAGES } from './api-errors';
import { isMockDataSourceFor, waitForMockDelay } from './data-source';
import { isWorkflowApiInstanceId, workflowAttachmentDownloadUrl, type UniversityWorkflowAttachment } from './universities-repository';

export type WorkflowAttachmentCategory = 'pdf' | 'image' | 'archive' | 'document' | 'spreadsheet' | 'other';

interface WorkflowFileTypeDefinition {
  label: string;
  extensions: readonly string[];
  mimeTypes: readonly string[];
  category: WorkflowAttachmentCategory;
  imagePreview: boolean;
  uploadAllowed: boolean;
}

/** One source of truth for accept, validation, list icons and preview support. */
export const WORKFLOW_FILE_TYPES: readonly WorkflowFileTypeDefinition[] = [
  { label: 'PNG', extensions: ['png'], mimeTypes: ['image/png'], category: 'image', imagePreview: true, uploadAllowed: true },
  { label: 'JPEG', extensions: ['jpg', 'jpeg'], mimeTypes: ['image/jpeg', 'image/jpg'], category: 'image', imagePreview: true, uploadAllowed: true },
  { label: 'GIF', extensions: ['gif'], mimeTypes: ['image/gif'], category: 'image', imagePreview: true, uploadAllowed: false },
  { label: 'WEBP', extensions: ['webp'], mimeTypes: ['image/webp'], category: 'image', imagePreview: true, uploadAllowed: false },
  { label: 'SVG', extensions: ['svg'], mimeTypes: ['image/svg+xml'], category: 'image', imagePreview: true, uploadAllowed: false },
  { label: 'PDF', extensions: ['pdf'], mimeTypes: ['application/pdf'], category: 'pdf', imagePreview: false, uploadAllowed: true },
  { label: 'ZIP', extensions: ['zip'], mimeTypes: ['application/zip', 'application/x-zip-compressed'], category: 'archive', imagePreview: false, uploadAllowed: true },
  { label: 'GZIP', extensions: ['gz', 'gzip'], mimeTypes: ['application/gzip', 'application/x-gzip'], category: 'archive', imagePreview: false, uploadAllowed: true },
  { label: 'RAR', extensions: ['rar'], mimeTypes: ['application/vnd.rar', 'application/x-rar-compressed'], category: 'archive', imagePreview: false, uploadAllowed: true },
  { label: '7Z', extensions: ['7z'], mimeTypes: ['application/x-7z-compressed'], category: 'archive', imagePreview: false, uploadAllowed: false },
  { label: 'TAR', extensions: ['tar'], mimeTypes: ['application/x-tar'], category: 'archive', imagePreview: false, uploadAllowed: false },
  { label: 'DOC', extensions: ['doc'], mimeTypes: ['application/msword'], category: 'document', imagePreview: false, uploadAllowed: true },
  { label: 'DOCX', extensions: ['docx'], mimeTypes: ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'], category: 'document', imagePreview: false, uploadAllowed: true },
  { label: 'TXT', extensions: ['txt'], mimeTypes: ['text/plain'], category: 'document', imagePreview: false, uploadAllowed: false },
  { label: 'RTF', extensions: ['rtf'], mimeTypes: ['application/rtf', 'text/rtf'], category: 'document', imagePreview: false, uploadAllowed: false },
  { label: 'ODT', extensions: ['odt'], mimeTypes: ['application/vnd.oasis.opendocument.text'], category: 'document', imagePreview: false, uploadAllowed: false },
  { label: 'XLS', extensions: ['xls'], mimeTypes: ['application/vnd.ms-excel'], category: 'spreadsheet', imagePreview: false, uploadAllowed: true },
  { label: 'XLSX', extensions: ['xlsx'], mimeTypes: ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'], category: 'spreadsheet', imagePreview: false, uploadAllowed: true },
  { label: 'CSV', extensions: ['csv'], mimeTypes: ['text/csv'], category: 'spreadsheet', imagePreview: false, uploadAllowed: false },
  { label: 'ODS', extensions: ['ods'], mimeTypes: ['application/vnd.oasis.opendocument.spreadsheet'], category: 'spreadsheet', imagePreview: false, uploadAllowed: false },
] as const;

export const MAX_UPLOAD_FILE_SIZE_BYTES = 50 * 1024 * 1024;
export const MAX_UPLOAD_FILENAME_LENGTH = 255;
export const WORKFLOW_ATTACHMENT_ACCEPT = [...new Set(WORKFLOW_FILE_TYPES.filter((item) => item.uploadAllowed).flatMap((item) => [
  ...item.extensions.map((extension) => `.${extension}`),
  ...item.mimeTypes,
]))].join(',');
export const WORKFLOW_ATTACHMENT_FORMATS_LABEL = WORKFLOW_FILE_TYPES.filter((item) => item.uploadAllowed).map((item) => item.label).join(', ');

function getFileExtension(fileName: string): string {
  const lastDot = fileName.lastIndexOf('.');
  return lastDot > 0 && lastDot < fileName.length - 1 ? fileName.slice(lastDot + 1).toLowerCase() : '';
}

function getFileTypeDefinition(mimeType?: string, fileName = ''): WorkflowFileTypeDefinition | undefined {
  const extension = getFileExtension(fileName);
  const mime = mimeType?.split(';', 1)[0]?.trim().toLowerCase() ?? '';
  return WORKFLOW_FILE_TYPES.find((item) => extension && item.extensions.includes(extension))
    ?? WORKFLOW_FILE_TYPES.find((item) => mime && item.mimeTypes.includes(mime));
}

export function getWorkflowAttachmentCategory(mimeType?: string, fileName = ''): WorkflowAttachmentCategory {
  return getFileTypeDefinition(mimeType, fileName)?.category ?? 'other';
}

export function getWorkflowAttachmentTypeLabel(mimeType?: string, fileName = ''): string {
  return getFileTypeDefinition(mimeType, fileName)?.label ?? (getFileExtension(fileName).toUpperCase() || 'Файл');
}

export function isWorkflowImageAttachment(mimeType?: string, fileName = ''): boolean {
  return getFileTypeDefinition(mimeType, fileName)?.imagePreview ?? false;
}

export type WorkflowUploadValidationErrorCode = 'empty' | 'too-large' | 'name' | 'type';
export type WorkflowUploadValidationResult =
  | { valid: true; type: WorkflowFileTypeDefinition }
  | { valid: false; code: WorkflowUploadValidationErrorCode; message: string };

const unsafeFilename = /[\u0000-\u001f\u007f/\\]/;

export function validateWorkflowUploadFile(file: Pick<File, 'name' | 'size' | 'type'>): WorkflowUploadValidationResult {
  const name = file.name.trim();
  if (!name || name === '.' || name === '..' || name.length > MAX_UPLOAD_FILENAME_LENGTH || unsafeFilename.test(file.name) || name !== file.name.replace(/^[ .]+|[ .]+$/g, '') || /^[a-zA-Z]:/.test(name)) {
    return { valid: false, code: 'name', message: 'Некорректное имя файла' };
  }
  if (file.size === 0) return { valid: false, code: 'empty', message: 'Файл пустой.' };
  if (file.size > MAX_UPLOAD_FILE_SIZE_BYTES) return { valid: false, code: 'too-large', message: ERROR_MESSAGES.FILE_TOO_LARGE };

  const extension = getFileExtension(name);
  const definition = WORKFLOW_FILE_TYPES.find((item) => item.uploadAllowed && item.extensions.includes(extension));
  if (!definition) return { valid: false, code: 'type', message: ERROR_MESSAGES.FILE_TYPE_NOT_ALLOWED };
  const mime = file.type.split(';', 1)[0].trim().toLowerCase();
  if (mime && !definition.mimeTypes.includes(mime)) return { valid: false, code: 'type', message: ERROR_MESSAGES.FILE_TYPE_NOT_ALLOWED };
  return { valid: true, type: definition };
}

export interface WorkflowAttachmentApiRecord {
  id: string;
  instance_id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  uploaded_by_keycloak_sub: string;
  created_at: string;
  updated_at: string;
}

export class WorkflowAttachmentUploadError extends ApiRequestError {
  constructor(status: number, body: unknown, message: string, transportMessage?: string) {
    super(status, body, message, transportMessage);
    this.name = 'WorkflowAttachmentUploadError';
  }
}

export async function uploadWorkflowAttachment(instanceId: string, file: File, options: { signal: AbortSignal; onProgress: (progress: number) => void }): Promise<WorkflowAttachmentApiRecord> {
  if (!isWorkflowApiInstanceId(instanceId)) throw new WorkflowAttachmentUploadError(0, undefined, 'Загрузка недоступна для этого Workflow.');
  if (isMockDataSourceFor('workflow')) {
    options.onProgress(15);
    await waitForMockDelay(options.signal);
    options.onProgress(100);
    const timestamp = new Date().toISOString();
    const suffix = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}`;
    return {
      id: `mock-attachment-${suffix}`,
      instance_id: instanceId,
      original_filename: file.name,
      mime_type: file.type || 'application/octet-stream',
      file_size: file.size,
      uploaded_by_keycloak_sub: 'mock-user',
      created_at: timestamp,
      updated_at: timestamp,
    };
  }
  const body = new FormData();
  body.append('file', file, file.name);
  const result = await apiUploadFormData<WorkflowAttachmentApiRecord>(`/api/v1/workflow/instances/${instanceId}/attachments`, body, options);
  if (!result.ok) throw new WorkflowAttachmentUploadError(result.status, result.body, 'Не удалось загрузить файл.', result.error);
  return result.data;
}

export function workflowAttachmentFromApi(record: WorkflowAttachmentApiRecord, user: AuthUser | null): UniversityWorkflowAttachment {
  const downloadUrl = workflowAttachmentDownloadUrl(record.instance_id, record.id) ?? undefined;
  return {
    id: record.id,
    fileName: record.original_filename,
    fileType: getWorkflowAttachmentTypeLabel(record.mime_type, record.original_filename),
    fileSize: '',
    mimeType: record.mime_type,
    fileSizeBytes: record.file_size,
    uploadedBy: user && user.id === record.uploaded_by_keycloak_sub ? { id: user.id, name: user.name, role: user.roleLabel } : { id: record.uploaded_by_keycloak_sub, name: '' },
    uploadedAt: record.created_at,
    downloadUrl,
    previewUrl: isWorkflowImageAttachment(record.mime_type, record.original_filename) ? downloadUrl : undefined,
    canDelete: true,
  };
}

export function canWriteWorkflowAttachments(user: AuthUser | null): boolean {
  return hasPermission(user, 'workflow.change_status');
}

export function canDeleteWorkflowAttachment(attachment: UniversityWorkflowAttachment, user: AuthUser | null): boolean {
  return Boolean(attachment.canDelete && canWriteWorkflowAttachments(user) && user
    && (hasRole(user, 'admin') || attachment.uploadedBy?.id === user.id));
}
