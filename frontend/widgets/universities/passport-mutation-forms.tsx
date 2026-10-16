'use client';

import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { catalogQueryKeys, getCatalogReferenceData } from '@/shared/lib/catalogs-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import {
  createUniversityMeeting,
  attachUniversityProduct,
  updateUniversityMeeting,
  type UniversityMeetingInput,
  type UniversityMeetingRow,
} from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Input, Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { SearchableSelect } from '@/shared/ui/rtk/multiselect';
import styles from './university-passport-sections.module.css';

function localDateTime(iso?: string): string {
  const date = iso ? new Date(iso) : new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function fieldError(errors: Record<string, string>, key: string) {
  return errors[key] ? <span className={styles.assignmentError} role="alert">{errors[key]}</span> : null;
}

export function ProductAssignmentForm({ universityId, existingProductIds, onClose, onSaved }: { universityId: string; existingProductIds: string[]; onClose: () => void; onSaved: () => void }) {
  const queryClient = useQueryClient();
  const references = useQuery({ queryKey: catalogQueryKeys.references, queryFn: () => getCatalogReferenceData(), staleTime: 30_000 });
  const [selectedId, setSelectedId] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const available = references.data?.products.filter((item) => !existingProductIds.includes(item.id)) ?? [];
  const save = useMutation({
    mutationFn: () => attachUniversityProduct(universityId, selectedId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.productsAll }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.passport(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.overview }),
        queryClient.invalidateQueries({ queryKey: queryKeys.audit.all }),
      ]);
      onSaved();
    },
    onError: (cause) => setMessage(normalizeApiError(cause).message),
  });
  return <Modal title="Добавить продукт ВУЗу" onClose={() => { if (!save.isPending) onClose(); }}><form className={styles.assignmentForm} onSubmit={(event) => { event.preventDefault(); if (!save.isPending && selectedId) save.mutate(); }}>
    <SearchableSelect label="Продукт из каталога" labelPlacement="outside" value={selectedId} disabled={references.isPending || references.isError} onChange={setSelectedId} options={available} placeholder="Выберите продукт" />
    {references.isError ? <p className={styles.assignmentError} role="alert">Не удалось загрузить каталог. <button type="button" onClick={() => void references.refetch()}>Повторить</button></p> : null}
    {references.isSuccess && !available.length ? <p>Все записи каталога уже закреплены за этим ВУЗом.</p> : null}
    {message ? <p className={styles.assignmentError} role="alert">{message}</p> : null}
    <div className={styles.assignmentActions}><Button type="button" variant="ghost" disabled={save.isPending} onClick={onClose}>Отмена</Button><Button type="submit" variant="primary" loading={save.isPending} disabled={!selectedId || save.isPending}>Добавить</Button></div>
  </form></Modal>;
}

export function MeetingMutationForm({ universityId, meeting, onClose, onSaved }: { universityId: string; meeting: UniversityMeetingRow | null; onClose: () => void; onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [type, setType] = useState<UniversityMeetingInput['type']>(meeting?.type ?? 'online');
  const [subject, setSubject] = useState(meeting?.subject ?? '');
  const [meetingAt, setMeetingAt] = useState(localDateTime(meeting?.occurredAt));
  const [participants, setParticipants] = useState(meeting?.participants.map((item) => item.name).join(', ') ?? '');
  const [outcome, setOutcome] = useState(meeting?.outcome === '—' ? '' : meeting?.outcome ?? '');
  const [nextAction, setNextAction] = useState(meeting?.nextAction === '—' ? '' : meeting?.nextAction ?? '');
  const [dueDate, setDueDate] = useState(meeting?.dueDate ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (input: UniversityMeetingInput) => meeting ? updateUniversityMeeting(meeting.id, input) : createUniversityMeeting(universityId, input),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.meetingsFamily(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.passport(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.historyFamily(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.audit.all }),
      ]);
      onSaved();
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (save.isPending) return;
    const nextErrors: Record<string, string> = {};
    if (!subject.trim()) nextErrors.subject = 'Укажите тему встречи.';
    if (!meetingAt || Number.isNaN(new Date(meetingAt).getTime())) nextErrors.meeting_at = 'Укажите дату и время.';
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setMessage(null);
    save.mutate({ type, subject, meetingAt: new Date(meetingAt).toISOString(), participants: participants.split(',').map((item) => item.trim()).filter(Boolean), outcome, nextAction, dueDate }, {
      onError: (cause) => {
        const normalized = normalizeApiError(cause);
        setErrors(Object.fromEntries(normalized.fieldErrors.map((field) => [field.field, field.message])));
        setMessage(normalized.message);
      },
    });
  };
  return <Modal title={meeting ? 'Редактировать встречу' : 'Добавить встречу'} onClose={() => { if (!save.isPending) onClose(); }}><form className={styles.assignmentForm} onSubmit={submit} noValidate>
    <label className={styles.filter}><span>Тип</span><Select value={type} onChange={(event) => setType(event.target.value as UniversityMeetingInput['type'])}><option value="online">Онлайн</option><option value="offline">Очно</option><option value="phone">Телефон</option><option value="email">Email</option></Select></label>
    <label className={styles.filter}><span>Тема *</span><Input value={subject} maxLength={1024} aria-invalid={Boolean(errors.subject)} onChange={(event) => setSubject(event.target.value)} />{fieldError(errors, 'subject')}</label>
    <label className={styles.filter}><span>Дата и время *</span><Input type="datetime-local" value={meetingAt} aria-invalid={Boolean(errors.meeting_at)} onChange={(event) => setMeetingAt(event.target.value)} />{fieldError(errors, 'meeting_at')}</label>
    <label className={styles.filter}><span>Участники через запятую</span><Input value={participants} onChange={(event) => setParticipants(event.target.value)} /></label>
    <label className={styles.filter}><span>Итог</span><TextArea rows={2} value={outcome} onChange={(event) => setOutcome(event.target.value)} /></label>
    <label className={styles.filter}><span>Следующее действие</span><TextArea rows={2} value={nextAction} onChange={(event) => setNextAction(event.target.value)} /></label>
    <label className={styles.filter}><span>Срок следующего действия</span><Input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label>
    {message ? <p className={styles.assignmentError} role="alert">{message}</p> : null}
    <div className={styles.assignmentActions}><Button type="button" variant="ghost" disabled={save.isPending} onClick={onClose}>Отмена</Button><Button type="submit" variant="primary" loading={save.isPending} disabled={save.isPending}>Сохранить</Button></div>
  </form></Modal>;
}
