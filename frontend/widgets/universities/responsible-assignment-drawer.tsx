'use client';

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { adminUsersQueryKeys, addUniversityResponsible, assignUniversityResponsible, listResponsibleCandidates, type ResponsibleCandidate } from '@/shared/lib/users-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { TextArea } from '@/shared/ui/rtk/form-controls';
import { SearchableSelect } from '@/shared/ui/rtk/multiselect';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { invalidateResponsibleQueries } from './responsible-queries';
import styles from './university-responsibles-section.module.css';

type Props = {
  id: string;
  primaryId: string;
  existingIds: string[];
  allowAdd: boolean;
  allowPrimary: boolean;
  onClose: () => void;
  onSuccess: () => void;
};

export function ResponsibleAssignmentDrawer({ id, primaryId, existingIds, allowAdd, allowPrimary, onClose, onSuccess }: Props) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState<ResponsibleCandidate | null>(null);
  const [makePrimary, setMakePrimary] = useState(!allowAdd);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedSearch(search), 250); return () => window.clearTimeout(timer); }, [search]);
  const candidatesQuery = useQuery({ queryKey: [...adminUsersQueryKeys.responsibleCandidates, debouncedSearch], queryFn: () => listResponsibleCandidates(debouncedSearch), staleTime: 30_000 });
  const candidates = candidatesQuery.data ?? [];
  const options = candidates.map((candidate) => ({ id: candidate.id, name: candidate.name, description: [candidate.role, candidate.email].filter(Boolean).join(' · ') }));
  if (selectedCandidate && !options.some((item) => item.id === selectedCandidate.id)) {
    options.unshift({ id: selectedCandidate.id, name: selectedCandidate.name, description: [selectedCandidate.role, selectedCandidate.email].filter(Boolean).join(' · ') });
  }
  const selectedId = selectedCandidate?.id ?? '';
  const alreadyAssigned = existingIds.includes(selectedId);
  const noChange = alreadyAssigned && (!makePrimary || selectedId === primaryId);
  const canSubmit = selectedId && !noChange && (makePrimary ? allowPrimary && reason.trim() : allowAdd);
  const mutation = useMutation({
    mutationFn: async () => {
      if (makePrimary) await assignUniversityResponsible({ universityId: id, responsibleId: selectedId, reason: reason.trim() });
      else await addUniversityResponsible(id, selectedId);
    },
    onSuccess: async () => { await invalidateResponsibleQueries(queryClient, id); onSuccess(); },
    onError: (cause) => { void invalidateResponsibleQueries(queryClient, id); setError(normalizeApiError(cause, { fallbackMessage: 'Не удалось сохранить назначение ответственного.' }).message); },
  });

  return <Drawer title="Добавить ответственного" onClose={() => { if (!mutation.isPending) onClose(); }}>
    <div className={styles.assignmentForm}>
      <p className={styles.assignmentIntro}>Выберите сотрудника. Поиск выполняется по ФИО и email во всём справочнике.</p>
      {candidatesQuery.isError ? <RouteErrorState compact onRetry={() => void candidatesQuery.refetch()} /> : <SearchableSelect label="Ответственный" labelPlacement="outside" value={selectedId} onChange={(value) => { setSelectedCandidate(candidates.find((item) => item.id === value) ?? (selectedCandidate?.id === value ? selectedCandidate : null)); setError(null); }} options={options} searchValue={search} onSearchChange={setSearch} remoteSearch loading={candidatesQuery.isPending} disabled={mutation.isPending} placeholder="Выберите ответственного" hint="Показаны первые 100 записей. Для поиска по всему справочнику введите ФИО или email." />}
      <label className={styles.primaryOption}>
        <input type="checkbox" checked={makePrimary} disabled={!allowPrimary || mutation.isPending} onChange={(event) => { setMakePrimary(event.target.checked); setError(null); }} />
        <span><strong>Сделать основным</strong><small>Он будет указан как главный контакт ВУЗа; прежний основной останется в списке ответственных.</small></span>
      </label>
      {makePrimary ? <label className={styles.reasonField}><span>Причина назначения</span><TextArea value={reason} onChange={(event) => setReason(event.target.value)} disabled={mutation.isPending} placeholder="Например, перераспределение зоны ответственности" rows={3} /></label> : null}
      {selectedId && noChange ? <p className={styles.assignmentHint}>{selectedId === primaryId ? 'Этот сотрудник уже назначен основным.' : 'Этот сотрудник уже назначен. Отметьте «Сделать основным», если хотите изменить его статус.'}</p> : null}
      {error ? <p className={styles.assignmentError} role="alert">{error}</p> : null}
      <div className={styles.actions}><Button variant="ghost" type="button" disabled={mutation.isPending} onClick={onClose}>Отмена</Button><Button variant="primary" type="button" loading={mutation.isPending} disabled={mutation.isPending || !canSubmit || candidatesQuery.isError} onClick={() => { setError(null); mutation.mutate(); }}>Сохранить</Button></div>
    </div>
  </Drawer>;
}
