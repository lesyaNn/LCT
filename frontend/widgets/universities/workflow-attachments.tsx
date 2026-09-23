'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import Image from 'next/image';
import Archive from '@atomaro/icons/24/document/Archive';
import ArrowLeft from '@atomaro/icons/24/navigation/ArrowLeft';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import Attachment from '@atomaro/icons/24/action/Attachment';
import CloseSmall from '@atomaro/icons/24/navigation/CloseSmall';
import CloudDownload from '@atomaro/icons/24/action/CloudDownload';
import DocumentImage from '@atomaro/icons/24/document/DocumentImage';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import RefreshSmall from '@atomaro/icons/24/action/RefreshSmall';
import Table from '@atomaro/icons/24/document/Table';
import Trash from '@atomaro/icons/24/action/Trash';
import Upload from '@atomaro/icons/24/action/Upload';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatRelativeDateRu, formatFileSize } from '@/shared/lib/formatters';
import { normalizeApiError, type NormalizedApiError } from '@/shared/lib/api-errors';
import type { SemanticIntent } from '@/shared/lib/status-semantics';
import { useAttachmentUploadQueue, type WorkflowUploadQueueItem, type WorkflowUploadStatus } from '@/shared/lib/workflow-attachment-upload-queue';
import { deleteWorkflowAttachment, isWorkflowApiInstanceId, workflowAttachmentDownloadUrl, type UniversityWorkflowAttachment } from '@/shared/lib/universities-repository';
import {
  canDeleteWorkflowAttachment,
  canWriteWorkflowAttachments,
  getWorkflowAttachmentCategory,
  getWorkflowAttachmentTypeLabel,
  isWorkflowImageAttachment,
  WORKFLOW_ATTACHMENT_ACCEPT,
  WORKFLOW_ATTACHMENT_FORMATS_LABEL,
  workflowAttachmentFromApi,
  type WorkflowAttachmentCategory,
} from '@/shared/lib/workflow-attachments';
import { addWorkflowAttachmentToCache, removeWorkflowAttachmentFromCache } from '@/shared/lib/workflow-cache';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { Modal } from '@/shared/ui/rtk/modal';
import { Progress } from '@/shared/ui/rtk/progress';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import styles from './workflow-attachments.module.css';

const attachmentIcons: Record<WorkflowAttachmentCategory, typeof DocumentText> = { pdf: DocumentText, image: DocumentImage, archive: Archive, document: DocumentText, spreadsheet: Table, other: Attachment };
const uploadStatus: Record<WorkflowUploadStatus, { label: string; intent: SemanticIntent }> = {
  queued: { label: 'В очереди', intent: 'neutral' },
  uploading: { label: 'Загрузка', intent: 'brand' },
  processing: { label: 'Обработка', intent: 'brand' },
  success: { label: 'Загружен', intent: 'success' },
  error: { label: 'Ошибка', intent: 'danger' },
  cancelled: { label: 'Отменён', intent: 'neutral' },
};

function AttachmentTypeIcon({ mimeType, fileName }: { mimeType?: string; fileName: string }) {
  const Icon = attachmentIcons[getWorkflowAttachmentCategory(mimeType, fileName)];
  return <Icon size={20} fill="currentColor" />;
}

function ImagePreviewModal({ images, selected, onClose, onSelect }: { images: UniversityWorkflowAttachment[]; selected: number; onClose: () => void; onSelect: (index: number) => void }) {
  const image = images[selected];
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'ArrowLeft') onSelect((selected - 1 + images.length) % images.length); if (event.key === 'ArrowRight') onSelect((selected + 1) % images.length); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [images.length, onSelect, selected]);
  if (!image?.previewUrl) return null;
  return <Modal title={image.fileName} size="l" onClose={onClose}><div className={styles.preview}><Image src={image.previewUrl} alt={image.description || image.fileName} width={1200} height={900} unoptimized /><div className={styles.previewControls}><Button variant="ghost" size="s" type="button" aria-label="Предыдущее изображение" onClick={() => onSelect((selected - 1 + images.length) % images.length)}><ArrowLeft size={16} fill="currentColor" />Предыдущее</Button><span>{selected + 1} из {images.length}</span><Button variant="ghost" size="s" type="button" aria-label="Следующее изображение" onClick={() => onSelect((selected + 1) % images.length)}>Следующее<ArrowRight size={16} fill="currentColor" /></Button></div></div></Modal>;
}

function AttachmentThumbnail({ attachment, onOpen }: { attachment: UniversityWorkflowAttachment; onOpen: () => void }) {
  if (!isWorkflowImageAttachment(attachment.mimeType, attachment.fileName) || !attachment.previewUrl) return <span className={styles.fileIcon} aria-hidden="true"><AttachmentTypeIcon mimeType={attachment.mimeType} fileName={attachment.fileName} /></span>;
  return <button className={styles.thumbnailButton} type="button" aria-label={`Открыть изображение ${attachment.fileName}`} onClick={onOpen}><Image src={attachment.previewUrl} alt="" width={96} height={96} unoptimized /></button>;
}

function AttachmentRow({ attachment, instanceId, canDelete, onOpen, onDelete }: { attachment: UniversityWorkflowAttachment; instanceId: string; canDelete: boolean; onOpen: () => void; onDelete: (attachment: UniversityWorkflowAttachment) => void }) {
  const downloadUrl = attachment.downloadUrl ?? workflowAttachmentDownloadUrl(instanceId, attachment.id);
  const size = formatFileSize(attachment.fileSizeBytes, attachment.fileSize);
  const fileType = attachment.fileType || getWorkflowAttachmentTypeLabel(attachment.mimeType, attachment.fileName);
  return <li className={styles.row}><AttachmentThumbnail attachment={attachment} onOpen={onOpen} /><div className={styles.info}><Tooltip content={<span>{attachment.fileName}</span>}><span className={styles.fileName} tabIndex={0}>{attachment.fileName}</span></Tooltip><div className={styles.meta}><span>{fileType}</span><span>{size}</span>{attachment.uploadedBy ? <span className={styles.uploader}><Avatar initials={attachment.uploadedBy.name.slice(0, 2).toLocaleUpperCase('ru-RU')} size="s" />Загрузил: {attachment.uploadedBy.name}</span> : null}{attachment.uploadedAt ? <time dateTime={attachment.uploadedAt}>{formatRelativeDateRu(attachment.uploadedAt)}</time> : null}</div>{attachment.description ? <p className={styles.description}>{attachment.description}</p> : null}</div><div className={styles.actions}>{downloadUrl ? <a className={styles.actionLink} href={downloadUrl} download aria-label={`Скачать ${attachment.fileName}`}><CloudDownload size={16} fill="currentColor" />Скачать</a> : <Button variant="ghost" size="s" type="button" disabled title="Скачивание подключится после появления API" aria-label={`Скачать ${attachment.fileName}`}><CloudDownload size={16} fill="currentColor" />Скачать</Button>}{canDelete ? <Button variant="ghost" size="s" type="button" aria-label={`Удалить ${attachment.fileName}`} onClick={() => onDelete(attachment)}><Trash size={16} fill="currentColor" />Удалить</Button> : null}</div></li>;
}

function AttachmentDropZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const addFileList = useCallback((files: FileList | null) => {
    if (files?.length) onFiles(Array.from(files));
  }, [onFiles]);
  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    addFileList(event.currentTarget.files);
    event.currentTarget.value = '';
  };
  const onDragEnter = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };
  const onDragLeave = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (!dragDepth.current) setDragging(false);
  };
  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    addFileList(event.dataTransfer.files);
  };
  return <label className={`${styles.dropZone} ${dragging ? styles.dropZoneActive : ''}`} onDragEnter={onDragEnter} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }} onDragLeave={onDragLeave} onDrop={onDrop}><input className={styles.dropInput} type="file" multiple accept={WORKFLOW_ATTACHMENT_ACCEPT} aria-label="Выбрать файлы для загрузки" onChange={onInputChange} /><span className={styles.dropIcon} aria-hidden="true"><Upload size={24} fill="currentColor" /></span><span className={styles.dropCopy}><strong>Перетащите файлы сюда</strong><span className={styles.dropHint}>{WORKFLOW_ATTACHMENT_FORMATS_LABEL} · до 50 MB на файл</span></span><span className={styles.chooseFiles}>Выбрать файлы</span></label>;
}

function UploadQueueRow({ item, onCancel, onRetry, onRemove }: { item: WorkflowUploadQueueItem; onCancel: () => void; onRetry: () => void; onRemove: () => void }) {
  const semantics = uploadStatus[item.status];
  const showProgress = item.status === 'uploading' || item.status === 'processing' || item.status === 'success';
  const canCancel = item.status === 'queued' || item.status === 'uploading' || item.status === 'processing';
  const errorId = item.error ? `${item.id}-error` : undefined;
  return <li className={styles.uploadRow} aria-describedby={errorId}><span className={styles.fileIcon} aria-hidden="true"><AttachmentTypeIcon mimeType={item.file.type} fileName={item.file.name} /></span><div className={styles.uploadInfo}><div className={styles.uploadHeader}><Tooltip content={<span>{item.file.name}</span>}><span className={styles.fileName} tabIndex={0}>{item.file.name}</span></Tooltip><StatusBadge intent={semantics.intent}>{semantics.label}</StatusBadge></div><div className={styles.meta}><span>{getWorkflowAttachmentTypeLabel(item.file.type, item.file.name)}</span><span>{formatFileSize(item.file.size)}</span></div>{showProgress ? <div className={styles.uploadProgress}><Progress value={item.progress} label={`${semantics.label}: ${item.file.name}`} /><span>{item.progress}%</span></div> : null}{item.error ? <p className={styles.uploadError} id={errorId} role="alert">{item.error}</p> : null}</div><div className={styles.uploadActions}>{canCancel ? <Button variant="ghost" size="s" type="button" aria-label={`Отменить загрузку ${item.file.name}`} onClick={onCancel}><CloseSmall size={16} fill="currentColor" />Отменить</Button> : null}{item.status === 'error' && !item.validationError ? <Button variant="ghost" size="s" type="button" onClick={onRetry}><RefreshSmall size={16} fill="currentColor" />Повторить</Button> : null}{item.status === 'error' ? <Button variant="ghost" size="s" type="button" aria-label={`Удалить ${item.file.name} из списка`} onClick={onRemove}><Trash size={16} fill="currentColor" />Удалить</Button> : null}</div></li>;
}

export function WorkflowAttachments({ instanceId, stageId, attachments, onNotify }: { instanceId: string; stageId: string; attachments: UniversityWorkflowAttachment[]; onNotify?: (notification: { intent: 'error'; title: string; message: string }) => void }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [deleteCandidate, setDeleteCandidate] = useState<UniversityWorkflowAttachment | null>(null);
  const [selectedImage, setSelectedImage] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const images = useMemo(() => attachments.filter((attachment) => isWorkflowImageAttachment(attachment.mimeType, attachment.fileName) && attachment.previewUrl), [attachments]);
  const handleUploadSuccess = useCallback((record: Parameters<typeof workflowAttachmentFromApi>[0]) => {
    addWorkflowAttachmentToCache(queryClient, instanceId, stageId, workflowAttachmentFromApi(record, user));
  }, [instanceId, queryClient, stageId, user]);
  const queue = useAttachmentUploadQueue({ instanceId, onSuccess: handleUploadSuccess, onServerError: (normalized: NormalizedApiError) => onNotify?.({ intent: 'error', title: 'Ошибка загрузки', message: normalized.message }) });
  const visibleAttachments = useMemo(() => {
    const temporarySuccessIds = new Set(queue.items.flatMap((item) => item.serverAttachmentId ? [item.serverAttachmentId] : []));
    return attachments.filter((attachment) => !temporarySuccessIds.has(attachment.id));
  }, [attachments, queue.items]);
  const canUpload = isWorkflowApiInstanceId(instanceId) && canWriteWorkflowAttachments(user);
  const remove = useMutation({
    mutationFn: (attachment: UniversityWorkflowAttachment) => deleteWorkflowAttachment(instanceId, attachment.id),
    onSuccess: (_data, attachment) => {
      removeWorkflowAttachmentFromCache(queryClient, instanceId, stageId, attachment.id);
      setDeleteCandidate(null);
      setSelectedImage(null);
    },
    onError: (cause: unknown) => { const normalized = normalizeApiError(cause); setError(normalized.message); onNotify?.({ intent: 'error', title: 'Ошибка удаления вложения', message: normalized.message }); },
  });
  const headingId = `${instanceId}-${stageId}-attachments-title`;
  return <section className={styles.section} aria-labelledby={headingId}><div className={styles.heading}><h3 id={headingId}><Attachment size={18} fill="currentColor" />Вложения <span className={styles.count}>{attachments.length}</span></h3></div>{canUpload ? <AttachmentDropZone onFiles={queue.addFiles} /> : null}{queue.items.length ? <ul className={styles.queueList} aria-label="Очередь загрузки">{queue.items.map((item) => <UploadQueueRow key={item.id} item={item} onCancel={() => queue.cancel(item.id)} onRetry={() => queue.retry(item.id)} onRemove={() => queue.remove(item.id)} />)}</ul> : null}{visibleAttachments.length ? <ul className={styles.list}>{visibleAttachments.map((attachment) => <AttachmentRow key={attachment.id} attachment={attachment} instanceId={instanceId} canDelete={canDeleteWorkflowAttachment(attachment, user) && isWorkflowApiInstanceId(instanceId)} onOpen={() => { const index = images.findIndex((image) => image.id === attachment.id); if (index >= 0) setSelectedImage(index); }} onDelete={setDeleteCandidate} />)}</ul> : !queue.items.length ? <EmptyState icon={<Attachment size={18} fill="currentColor" />} title="Вложений пока нет" description={canUpload ? 'Перетащите файлы в область выше или выберите их вручную.' : 'Файлы появятся здесь после загрузки.'} headingLevel={3} /> : null}{deleteCandidate ? <Modal title="Удалить вложение?" onClose={() => setDeleteCandidate(null)}><p className={styles.confirmText}>Файл «{deleteCandidate.fileName}» будет удалён. Это действие нельзя отменить.</p><div className={styles.confirmActions}><Button variant="ghost" size="s" type="button" onClick={() => setDeleteCandidate(null)}>Отмена</Button><Button variant="danger" size="s" type="button" loading={remove.isPending} disabled={remove.isPending} onClick={() => { setError(null); remove.mutate(deleteCandidate); }}>Удалить</Button></div>{error ? <p className={styles.error} role="alert">{error}</p> : null}</Modal> : null}{selectedImage !== null ? <ImagePreviewModal images={images} selected={selectedImage} onClose={() => setSelectedImage(null)} onSelect={setSelectedImage} /> : null}</section>;
}
