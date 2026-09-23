'use client';

import { useMemo, useState } from 'react';
import Download from '@atomaro/icons/24/action/Download';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import { formatDateRu, formatDaysUntilRu } from '@/shared/lib/formatters';
import { certificateStatusIntent, certificateStatusLabels } from '@/shared/lib/status-semantics';
import type { TeacherCertificate } from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { PassportDataTable, type PassportMobileField, type PassportTableColumn } from '@/widgets/universities/passport-data-table';
import { CertificateTimeline } from './certificate-timeline';
import styles from './teacher-passport.module.css';

type CertificateFilter = 'all' | 'mandatory';

function CertificateStatus({ row }: { row: TeacherCertificate }) {
  return <div className={row.mandatory && row.status === 'expired' ? styles.criticalStatus : styles.statusCell}><span className={styles.statusWithIcon}>{row.mandatory && row.status === 'expired' ? <ErrorStroke size={16} fill="currentColor" aria-hidden="true" /> : null}<StatusBadge intent={certificateStatusIntent[row.status]}>{certificateStatusLabels[row.status]}</StatusBadge></span>{row.status === 'expires_soon' || row.status === 'expired' ? <span className={styles.statusContext}>{row.expiresAt ? formatDaysUntilRu(row.expiresAt) : 'Срок не указан'}</span> : null}</div>;
}

function MandatoryBadge({ mandatory }: { mandatory: boolean }) {
  return <StatusBadge intent={mandatory ? 'brand' : 'neutral'}>{mandatory ? 'Да' : 'Нет'}</StatusBadge>;
}

function CertificateDocument({ document }: { document: TeacherCertificate['document'] }) {
  if (!document) return <span className={styles.muted}>Не приложен</span>;
  return <div className={styles.documentCell}><DocumentText size={20} fill="currentColor" aria-hidden="true" /><div className={styles.documentInfo}><strong>{document.name}</strong><span>{document.fileType} · {document.fileSize}</span></div>{document.downloadUrl ? <a className={styles.iconAction} href={document.downloadUrl} download aria-label={`Скачать ${document.name}`}><Download size={17} fill="currentColor" /></a> : null}</div>;
}

function CertificateDetails({ certificate, onClose }: { certificate: TeacherCertificate; onClose: () => void }) {
  return <section className={styles.detailPanel} aria-labelledby="teacher-certificate-detail-title"><div className={styles.detailHeader}><div><p className={styles.overline}>Детали сертификата</p><h3 id="teacher-certificate-detail-title">{certificate.name}</h3></div><Button variant="ghost" size="s" type="button" onClick={onClose}>Закрыть</Button></div><dl className={styles.detailGrid}><div><dt>Кем выдан</dt><dd>{certificate.issuer}</dd></div><div><dt>Выдан</dt><dd>{formatDateRu(certificate.issuedAt)}</dd></div><div><dt>Истекает</dt><dd>{certificate.expiresAt ? formatDateRu(certificate.expiresAt) : 'Бессрочно'}</dd></div><div><dt>Обязательный</dt><dd><MandatoryBadge mandatory={certificate.mandatory} /></dd></div><div><dt>Программа</dt><dd>{certificate.program ?? 'Без программы'}</dd></div><div><dt>Статус</dt><dd><StatusBadge intent={certificateStatusIntent[certificate.status]}>{certificateStatusLabels[certificate.status]}</StatusBadge></dd></div><div><dt>Документ</dt><dd><CertificateDocument document={certificate.document} /></dd></div></dl></section>;
}

export function TeacherCertificatesSection({ rows }: { rows: TeacherCertificate[] }) {
  const [filter, setFilter] = useState<CertificateFilter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const filteredRows = useMemo(() => rows.filter((row) => filter === 'all' || row.mandatory), [filter, rows]);
  const selectedCertificate = useMemo(() => filteredRows.find((row) => row.id === selectedId) ?? null, [filteredRows, selectedId]);
  const emptyMessage = filter === 'mandatory' ? 'Обязательных сертификатов нет' : 'Сертификаты пока не добавлены';
  const columns: PassportTableColumn<TeacherCertificate>[] = [
    { id: 'name', label: 'Сертификат', sortable: true, sortValue: (row) => row.name, render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { id: 'issuer', label: 'Кем выдан', sortable: true, sortValue: (row) => row.issuer, render: (row) => row.issuer },
    { id: 'issuedAt', label: 'Выдан', sortable: true, sortValue: (row) => row.issuedAt, render: (row) => formatDateRu(row.issuedAt) },
    { id: 'expiresAt', label: 'Истекает', sortable: true, sortValue: (row) => row.expiresAt ?? '9999-12-31', render: (row) => row.expiresAt ? formatDateRu(row.expiresAt) : 'Бессрочно' },
    { id: 'mandatory', label: 'Обязательный', sortable: true, sortValue: (row) => Number(row.mandatory), render: (row) => <MandatoryBadge mandatory={row.mandatory} /> },
    { id: 'program', label: 'Программа', sortable: true, sortValue: (row) => row.program ?? 'Без программы', render: (row) => row.program ?? 'Без программы' },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => row.status, render: (row) => <CertificateStatus row={row} /> },
    { id: 'actions', label: 'Действия', render: (row) => <div className={styles.rowActions}><Button variant="ghost" size="s" type="button" onClick={() => setSelectedId(row.id)}>Просмотреть</Button>{row.document?.downloadUrl ? <a className={styles.iconAction} href={row.document.downloadUrl} download aria-label={`Скачать копию сертификата ${row.name}`}><Download size={17} fill="currentColor" /></a> : null}</div> },
  ];
  const mobileFields: PassportMobileField<TeacherCertificate>[] = [
    { label: 'Сертификат', render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { label: 'Статус', render: (row) => <CertificateStatus row={row} /> },
    { label: 'Обязательный', render: (row) => <MandatoryBadge mandatory={row.mandatory} /> },
    { label: 'Кем выдан', render: (row) => row.issuer },
    { label: 'Истекает', render: (row) => row.expiresAt ? formatDateRu(row.expiresAt) : 'Бессрочно' },
    { label: 'Программа', render: (row) => row.program ?? 'Без программы' },
    { label: 'Действия', render: (row) => <div className={styles.rowActions}><Button variant="ghost" size="s" type="button" onClick={() => setSelectedId(row.id)}>Просмотреть</Button>{row.document?.downloadUrl ? <a className={styles.iconAction} href={row.document.downloadUrl} download aria-label={`Скачать копию сертификата ${row.name}`}><Download size={17} fill="currentColor" /></a> : null}</div> },
  ];
  return <section className={styles.section} aria-labelledby="teacher-certificates-title"><div className={styles.sectionHeading}><div><h2 id="teacher-certificates-title">Сертификаты</h2><p>Обязательные сертификаты влияют на готовность преподавателя и Health Score вуза.</p></div><label className={styles.filter}><span>Показать</span><select value={filter} onChange={(event) => { setFilter(event.target.value as CertificateFilter); setSelectedId(null); }}><option value="all">Все</option><option value="mandatory">Только обязательные</option></select></label></div>{selectedCertificate ? <CertificateDetails certificate={selectedCertificate} onClose={() => setSelectedId(null)} /> : null}{filteredRows.length ? <><PassportDataTable rows={filteredRows} columns={columns} mobileFields={mobileFields} groupBy={(row) => row.program ?? 'Без программы'} emptyMessage={emptyMessage} /><CertificateTimeline certificates={filteredRows} /></> : <div className={styles.emptyMessage} role="status">{emptyMessage}</div>}</section>;
}
