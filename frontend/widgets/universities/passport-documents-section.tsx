'use client';

import { useRef, useState, type ChangeEvent } from 'react';
import { FilePreview } from '@/shared/ui/file-preview/file-preview';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Edit from '@atomaro/icons/24/editor/Edit';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { canMutateCatalog, catalogQueryKeys, deleteContractFile, downloadContractFile, listCatalogItems, updateCatalogItem, uploadContractFile, type ContractCatalogItem, type ContractStatusRaw, type TransferStatus } from '@/shared/lib/catalogs-repository';
import { createUniversityDocument, downloadUniversityDocument, getUniversityDocuments, universityDocumentsQueryKey, universityPassportQueryKey, type UniversityDocumentRow, type UniversityDocumentType } from '@/shared/lib/universities-repository';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { MAX_UPLOAD_FILE_SIZE_BYTES } from '@/shared/lib/workflow-attachments';
import { downloadBlob } from '@/shared/lib/download-blob';
import { formatDateRu } from '@/shared/lib/formatters';
import { PassportDataTable, PassportTableSkeleton, type PassportTableColumn, type PassportMobileField } from './passport-data-table';
import { Button } from '@/shared/ui/rtk/button';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { CopyButton } from '@/shared/ui/rtk/copy-button';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { PassportSectionHeader } from './passport-section-header';
import styles from './university-passport-sections.module.css';

const statusNames: Record<ContractStatusRaw, string> = { draft: 'Черновик', signed: 'Подписан', terminated: 'Расторгнут' };
const effectiveStatusNames: Record<string, string> = { draft: 'Черновик', signed: 'Подписан', active: 'Действует', expires_soon: 'Скоро истекает', expired: 'Истёк', terminated: 'Расторгнут' };
const typeNames: Record<UniversityDocumentType, string> = { act: 'Акт', protocol: 'Протокол', other: 'Иное', contract: 'Договор', license: 'Лицензия' };

function validateDocumentFile(file: File): string | null {
  if (!file.name.trim()) return 'У файла должно быть название.';
  if (!file.size) return 'Файл пустой.';
  if (file.size > MAX_UPLOAD_FILE_SIZE_BYTES) return 'Файл больше 50 МБ.';
  return null;
}

export function PassportDocumentsSection({ id }: { id: string }) {
  const { user } = useAuth();
  const client = useQueryClient();
  const [tab, setTab] = useState<'contracts' | 'documents'>('contracts');
  const [page, setPage] = useState(1);
  const [documentPage, setDocumentPage] = useState(1);
  const [editing, setEditing] = useState<ContractCatalogItem | null>(null);
  const [status, setStatus] = useState<ContractStatusRaw>('signed');
  const [signedAt, setSignedAt] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const contractPickerRef = useRef<HTMLInputElement>(null);
  const documentPickerRef = useRef<HTMLInputElement>(null);
  const contractTargetRef = useRef<string | null>(null);
  const contractUploadGuard = useRef(false);
  const documentUploadGuard = useRef(false);
  const [documentTitle, setDocumentTitle] = useState('');
  const [documentType, setDocumentType] = useState<UniversityDocumentType | ''>('');
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const canEditContract = canMutateCatalog(user);
  const canCreateDocument = hasPermission(user, 'university.edit');
  const contracts = useQuery({ queryKey: [...catalogQueryKeys.list('agreements', { type: 'agreements', agreementKind: 'contracts', universityId: id, search: '', page, pageSize: 20 })], queryFn: ({ signal }) => listCatalogItems({ type: 'agreements', agreementKind: 'contracts', universityId: id, search: '', page, pageSize: 20 }, signal), enabled: tab === 'contracts' });
  const documents = useQuery({ queryKey: [...universityDocumentsQueryKey(id), documentPage, '', 'all', 'all'], queryFn: ({ signal }) => getUniversityDocuments(id, documentPage, 20, '', 'all', 'all', signal), enabled: tab === 'documents' });
  const refreshContracts = async () => { await client.invalidateQueries({ queryKey: catalogQueryKeys.family('agreements') }); };
  const refreshDocuments = async () => { await Promise.all([client.invalidateQueries({ queryKey: universityDocumentsQueryKey(id) }), client.invalidateQueries({ queryKey: universityPassportQueryKey(id) })]); };
  const save = useMutation({ mutationFn: () => updateCatalogItem(editing!.id, { type: 'agreements', kind: 'contracts', universityId: id, productId: editing!.productId, contractNumber: editing!.contractNumber, signedAt, expiresAt, statusRaw: status, transferStatus: editing!.transferStatus as TransferStatus, comment: editing!.comment }), onSuccess: async () => { setEditing(null); await refreshContracts(); }, onError: (cause) => setError(normalizeApiError(cause).message) });
  const upload = useMutation({ mutationFn: ({ contractId, file }: { contractId: string; file: File }) => uploadContractFile(contractId, file), onSuccess: refreshContracts, onError: (cause) => setError(normalizeApiError(cause).message), onSettled: () => { contractUploadGuard.current = false; } });
  const addDocument = useMutation({ mutationFn: (input: { type: UniversityDocumentType; title: string; file: File }) => createUniversityDocument(id, input), onSuccess: async () => { setDocumentTitle(''); setDocumentType(''); setDocumentFile(null); setDocumentPage(1); await refreshDocuments(); }, onError: (cause) => setError(normalizeApiError(cause).message), onSettled: () => { documentUploadGuard.current = false; } });
  const openEdit = (row: ContractCatalogItem) => { setError(''); setEditing(row); setStatus(row.statusRaw); setSignedAt(row.signedAt); setExpiresAt(row.expiresAt); };
  const openFile = (row: ContractCatalogItem) => { if (contractUploadGuard.current) return; setError(''); contractTargetRef.current = row.id; contractPickerRef.current?.click(); };
  const selectContractFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    if (!file || !contractTargetRef.current || contractUploadGuard.current) return;
    const validationError = validateDocumentFile(file);
    if (validationError) { setError(validationError); return; }
    setError('');
    contractUploadGuard.current = true;
    upload.mutate({ contractId: contractTargetRef.current, file });
  };
  const selectDocumentFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    if (!file || documentUploadGuard.current) return;
    const validationError = validateDocumentFile(file);
    if (validationError) { setError(validationError); return; }
    setError('');
    setDocumentFile(file);
  };
  const submitDocument = () => {
    if (!documentFile || !documentType || !documentTitle.trim() || documentUploadGuard.current) return;
    setError('');
    documentUploadGuard.current = true;
    addDocument.mutate({ type: documentType, title: documentTitle.trim(), file: documentFile });
  };
  const getFile = async (row: ContractCatalogItem) => { try { downloadBlob(await downloadContractFile(row.id), row.fileName); } catch (cause) { setError(normalizeApiError(cause).message); } };
  const getDocument = async (row: UniversityDocumentRow) => { try { downloadBlob(await downloadUniversityDocument(id, row.id), row.fileName); } catch (cause) { setError(normalizeApiError(cause).message); } };
  const removeFile = async (row: ContractCatalogItem) => { try { await deleteContractFile(row.id); await refreshContracts(); } catch (cause) { setError(normalizeApiError(cause).message); } };
  const contractColumns: PassportTableColumn<ContractCatalogItem>[] = [
    { id: 'number', label: 'Номер', render: (row) => <div className={styles.copyValue}><strong className={styles.primaryCell}>{row.contractNumber}</strong><span className={styles.copyAction}><Tooltip content="Копировать номер"><CopyButton className={styles.copyButton} value={row.contractNumber} label={`Копировать номер договора ${row.contractNumber}`} /></Tooltip></span></div> },
    { id: 'status', label: 'Статус', render: (row) => <StatusBadge intent={row.status === 'terminated' || row.status === 'expired' ? 'danger' : row.status === 'draft' ? 'neutral' : 'success'}>{effectiveStatusNames[row.status] ?? row.status}</StatusBadge> },
    { id: 'signed', label: 'Подписан', render: (row) => formatDateRu(row.signedAt) },
    { id: 'expires', label: 'Действует до', render: (row) => row.expiresAt ? formatDateRu(row.expiresAt) : '—' },
    { id: 'product', label: 'ИТ-продукт', render: (row) => row.productName || '—' },
    { id: 'file', label: 'Файл', render: (row) => row.fileName ? <FilePreview path={`/api/v1/contracts/${row.id}/file/preview`} name={row.fileName} size={row.fileSize ?? undefined} version={row.updatedAt}><button className={styles.fileNameButton} type="button" onClick={() => void getFile(row)}>{row.fileName}</button></FilePreview> : '—' },
    ...(canEditContract ? [{ id: 'actions', label: 'Действия', render: (row: ContractCatalogItem) => <div className={styles.documentFormActions}><Tooltip content="Редактировать"><IconButton icon={<Edit size={18} fill="currentColor" />} label="Редактировать" onClick={() => openEdit(row)} /></Tooltip><Button variant="ghost" size="s" type="button" disabled={upload.isPending} loading={upload.isPending && upload.variables?.contractId === row.id} onClick={() => openFile(row)}>{row.fileName ? 'Заменить файл' : 'Прикрепить файл'}</Button>{row.fileName ? <Button variant="ghost" size="s" type="button" disabled={upload.isPending} onClick={() => void removeFile(row)}>Удалить файл</Button> : null}</div> }] : []),
  ];
  const contractMobile: PassportMobileField<ContractCatalogItem>[] = contractColumns.filter((column) => column.id !== 'actions').map((column) => ({ label: column.label, render: column.render }));
  if (canEditContract) contractMobile.push({ label: 'Действия', render: (row) => <div className={styles.documentFormActions}><Button variant="ghost" size="s" type="button" onClick={() => openEdit(row)}>Редактировать</Button><Button variant="ghost" size="s" type="button" disabled={upload.isPending} loading={upload.isPending && upload.variables?.contractId === row.id} onClick={() => openFile(row)}>{row.fileName ? 'Заменить файл' : 'Прикрепить файл'}</Button></div> });
  const documentColumns: PassportTableColumn<UniversityDocumentRow>[] = [
    { id: 'name', label: 'Название', render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { id: 'type', label: 'Тип', render: (row) => typeNames[row.type as UniversityDocumentType] ?? row.type },
    { id: 'file', label: 'Файл', render: (row) => row.hasFile ? <FilePreview path={`/api/v1/universities/${id}/passport/documents/${row.id}/preview`} name={row.fileName} size={row.fileSize}><button className={styles.fileNameButton} type="button" onClick={() => void getDocument(row)}>{row.fileName}</button></FilePreview> : '—' },
    { id: 'status', label: 'Статус', render: (row) => row.status === 'archived' ? 'В архиве' : row.status === 'signed' ? 'Подписан' : 'Черновик' },
    { id: 'created', label: 'Дата добавления', render: (row) => formatDateRu(row.uploadedAt) },
  ];
  const documentMobile: PassportMobileField<UniversityDocumentRow>[] = documentColumns.map((column) => ({ label: column.label, render: column.render }));
  const contractRows = (contracts.data?.items ?? []).filter((row): row is ContractCatalogItem => row.type === 'agreements' && row.kind === 'contracts');
  const inlineDocumentForm = tab === 'documents' && documentFile ? <form className={`${styles.documentForm} ${styles.documentInlineForm}`} onSubmit={(event) => { event.preventDefault(); submitDocument(); }}><div className={styles.selectedDocument}><span title={documentFile.name}>{documentFile.name}</span><Button variant="ghost" size="s" type="button" disabled={addDocument.isPending} onClick={() => documentPickerRef.current?.click()}>Заменить</Button></div><div className={styles.documentInlineFields}><label>Название<Input required maxLength={1024} value={documentTitle} onChange={(event) => setDocumentTitle(event.target.value)} /></label><label>Тип<Select required value={documentType} onChange={(event) => setDocumentType(event.target.value as UniversityDocumentType | '')}><option value="">Выберите тип</option><option value="act">Акт</option><option value="protocol">Протокол</option><option value="other">Иное</option></Select></label></div><div className={styles.documentFormActions}><Button variant="ghost" size="s" type="button" disabled={addDocument.isPending} onClick={() => { setDocumentFile(null); setDocumentTitle(''); setDocumentType(''); setError(''); }}>Отмена</Button><Button variant="primary" size="s" type="submit" disabled={!documentTitle.trim() || !documentType || addDocument.isPending} loading={addDocument.isPending}>Загрузить документ</Button></div></form> : null;
  return <section className={styles.section} aria-label="Документы"><PassportSectionHeader title="Документы" count={tab === 'contracts' ? contracts.data?.total : documents.data?.total} actions={<><Button variant={tab === 'contracts' ? 'primary' : 'ghost'} size="s" type="button" onClick={() => setTab('contracts')}>Договоры</Button><Button variant={tab === 'documents' ? 'primary' : 'ghost'} size="s" type="button" onClick={() => setTab('documents')}>Прочие документы</Button>{tab === 'documents' && canCreateDocument ? <Button variant="primary" size="s" type="button" disabled={addDocument.isPending} onClick={() => { setError(''); documentPickerRef.current?.click(); }}>Добавить документ</Button> : null}</>} />
    <input ref={contractPickerRef} className={styles.filePickerInput} type="file" aria-label="Выбрать файл договора" onChange={selectContractFile} />
    <input ref={documentPickerRef} className={styles.filePickerInput} type="file" aria-label="Выбрать документ" onChange={selectDocumentFile} />
    {error ? <p className={styles.fileError} role="alert">{error}</p> : null}
    {inlineDocumentForm}
    {tab === 'contracts' ? contracts.isPending ? <PassportTableSkeleton /> : contracts.isError ? <RouteErrorState compact onRetry={() => void contracts.refetch()} /> : <PassportDataTable rows={contractRows} columns={contractColumns} mobileFields={contractMobile} emptyMessage="Договоры отсутствуют" serverPagination={{ page, pageSize: 20, total: contracts.data?.total ?? 0, onPageChange: setPage }} /> : documents.isPending ? <PassportTableSkeleton /> : documents.isError ? <RouteErrorState compact onRetry={() => void documents.refetch()} /> : <PassportDataTable rows={documents.data?.items ?? []} columns={documentColumns} mobileFields={documentMobile} emptyMessage="Документы отсутствуют" serverPagination={{ page: documentPage, pageSize: 20, total: documents.data?.total ?? 0, onPageChange: setDocumentPage }} />}
    {editing ? <Modal title={`Редактировать договор №${editing.contractNumber}`} onClose={() => setEditing(null)}><form className={styles.documentForm} onSubmit={(event) => { event.preventDefault(); save.mutate(); }}><label>Статус<Select value={status} onChange={(event) => setStatus(event.target.value as ContractStatusRaw)}>{Object.entries(statusNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></label><label>Дата подписания<Input type="date" required value={signedAt} onChange={(event) => setSignedAt(event.target.value)} /></label><label>Действует до<Input type="date" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} /></label>{error ? <p className={styles.fileError} role="alert">{error}</p> : null}<div className={styles.documentFormActions}><Button variant="ghost" size="s" type="button" onClick={() => setEditing(null)}>Отмена</Button><Button variant="primary" size="s" type="submit" loading={save.isPending}>Сохранить</Button></div></form></Modal> : null}
  </section>;
}
