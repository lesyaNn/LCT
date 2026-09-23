'use client';

import { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import Archive from '@atomaro/icons/24/document/Archive';
import ArrowLeft from '@atomaro/icons/24/navigation/ArrowLeft';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import Attachment from '@atomaro/icons/24/action/Attachment';
import CloudDownload from '@atomaro/icons/24/action/CloudDownload';
import DocumentImage from '@atomaro/icons/24/document/DocumentImage';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Table from '@atomaro/icons/24/document/Table';
import Trash from '@atomaro/icons/24/action/Trash';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatRelativeDateRu, formatFileSize } from '@/shared/lib/formatters';
import { deleteWorkflowAttachment, isWorkflowApiInstanceId, workflowAttachmentDownloadUrl, workflowQueryKey, type UniversityWorkflowAttachment } from '@/shared/lib/universities-repository';
import { canDeleteWorkflowAttachment, getWorkflowAttachmentCategory, isWorkflowImageAttachment, type WorkflowAttachmentCategory } from '@/shared/lib/workflow-attachments';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { Modal } from '@/shared/ui/rtk/modal';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import styles from './workflow-attachments.module.css';

const attachmentIcons: Record<WorkflowAttachmentCategory, typeof DocumentText> = { pdf: DocumentText, image: DocumentImage, archive: Archive, document: DocumentText, spreadsheet: Table, other: Attachment };

function AttachmentTypeIcon({ attachment }: { attachment: UniversityWorkflowAttachment }) {
  const Icon = attachmentIcons[getWorkflowAttachmentCategory(attachment.mimeType, attachment.fileName)];
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
  if (!isWorkflowImageAttachment(attachment.mimeType, attachment.fileName) || !attachment.previewUrl) return <span className={styles.fileIcon} aria-hidden="true"><AttachmentTypeIcon attachment={attachment} /></span>;
  return <button className={styles.thumbnailButton} type="button" aria-label={`Открыть изображение ${attachment.fileName}`} onClick={onOpen}><Image src={attachment.previewUrl} alt="" width={96} height={96} unoptimized /></button>;
}

function AttachmentRow({ attachment, instanceId, canDelete, onOpen, onDelete }: { attachment: UniversityWorkflowAttachment; instanceId: string; canDelete: boolean; onOpen: () => void; onDelete: (attachment: UniversityWorkflowAttachment) => void }) {
  const downloadUrl = attachment.downloadUrl ?? workflowAttachmentDownloadUrl(instanceId, attachment.id);
  const size = formatFileSize(attachment.fileSizeBytes, attachment.fileSize);
  return <li className={styles.row}><AttachmentThumbnail attachment={attachment} onOpen={onOpen} /><div className={styles.info}><Tooltip content={<span>{attachment.fileName}</span>}><span className={styles.fileName} tabIndex={0}>{attachment.fileName}</span></Tooltip><div className={styles.meta}><span>{size}</span>{attachment.uploadedBy ? <span className={styles.uploader}><Avatar initials={attachment.uploadedBy.name.slice(0, 2).toLocaleUpperCase('ru-RU')} size="s" />Загрузил: {attachment.uploadedBy.name}</span> : null}{attachment.uploadedAt ? <time dateTime={attachment.uploadedAt}>{formatRelativeDateRu(attachment.uploadedAt)}</time> : null}</div>{attachment.description ? <p className={styles.description}>{attachment.description}</p> : null}</div><div className={styles.actions}>{downloadUrl ? <a className={styles.actionLink} href={downloadUrl} download aria-label={`Скачать ${attachment.fileName}`}><CloudDownload size={16} fill="currentColor" />Скачать</a> : <Button variant="ghost" size="s" type="button" disabled title="Скачивание подключится после появления API" aria-label={`Скачать ${attachment.fileName}`}><CloudDownload size={16} fill="currentColor" />Скачать</Button>}{canDelete ? <Button variant="ghost" size="s" type="button" aria-label={`Удалить ${attachment.fileName}`} onClick={() => onDelete(attachment)}><Trash size={16} fill="currentColor" />Удалить</Button> : null}</div></li>;
}

export function WorkflowAttachments({ instanceId, attachments }: { instanceId: string; attachments: UniversityWorkflowAttachment[] }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [deleteCandidate, setDeleteCandidate] = useState<UniversityWorkflowAttachment | null>(null);
  const [selectedImage, setSelectedImage] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const images = useMemo(() => attachments.filter((attachment) => isWorkflowImageAttachment(attachment.mimeType, attachment.fileName) && attachment.previewUrl), [attachments]);
  const remove = useMutation({ mutationFn: (attachment: UniversityWorkflowAttachment) => deleteWorkflowAttachment(instanceId, attachment.id), onSuccess: async () => { setDeleteCandidate(null); await queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }); }, onError: (cause: Error) => setError(cause.message) });
  return <section className={styles.section} aria-labelledby={`${instanceId}-attachments-title`}><div className={styles.heading}><h3 id={`${instanceId}-attachments-title`}><Attachment size={18} fill="currentColor" />Вложения <span className={styles.count}>{attachments.length}</span></h3></div>{attachments.length ? <ul className={styles.list}>{attachments.map((attachment) => <AttachmentRow key={attachment.id} attachment={attachment} instanceId={instanceId} canDelete={canDeleteWorkflowAttachment(attachment, user) && isWorkflowApiInstanceId(instanceId)} onOpen={() => { const index = images.findIndex((image) => image.id === attachment.id); if (index >= 0) setSelectedImage(index); }} onDelete={setDeleteCandidate} />)}</ul> : <p className={styles.empty}>Вложений пока нет</p>}{deleteCandidate ? <Modal title="Удалить вложение?" onClose={() => setDeleteCandidate(null)}><p className={styles.confirmText}>Файл «{deleteCandidate.fileName}» будет удалён. Это действие нельзя отменить.</p><div className={styles.confirmActions}><Button variant="ghost" size="s" type="button" onClick={() => setDeleteCandidate(null)}>Отмена</Button><Button variant="primary" size="s" type="button" disabled={remove.isPending} onClick={() => { setError(null); remove.mutate(deleteCandidate); }}>{remove.isPending ? 'Удаление…' : 'Удалить'}</Button></div>{error ? <p className={styles.error} role="alert">{error}</p> : null}</Modal> : null}{selectedImage !== null ? <ImagePreviewModal images={images} selected={selectedImage} onClose={() => setSelectedImage(null)} onSelect={setSelectedImage} /> : null}</section>;
}
