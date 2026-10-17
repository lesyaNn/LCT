'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { queryKeys } from '@/shared/lib/query-keys';
import {
  attachUniversityProgram,
  createProgramWorkflow,
  getWorkflowSelectorPrograms,
  workflowProgramsQueryKey,
  type WorkflowInstanceApiRecord,
} from '@/shared/lib/universities-repository';
import {
  listWizardDirections,
  listWizardProducts,
  listWizardPrograms,
  universityWorkflowInstancesQueryKey,
  wizardDirectionsQueryKey,
  wizardProductLabel,
  wizardProductsQueryKey,
  wizardProgramsQueryKey,
} from '@/shared/lib/workflow-creation-repository';
import { listWorkflowTemplates, workflowTemplateListQueryKey } from '@/shared/lib/workflow-templates-repository';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner } from '@/shared/ui/rtk/form-field';
import { SearchableSelect } from '@/shared/ui/rtk/multiselect';
import { Modal } from '@/shared/ui/rtk/modal';
import { Skeleton, SkeletonGroup } from '@/shared/ui/skeleton';
import styles from './workflow-transition-modal.module.css';

export function WorkflowCreateModal({ universityId, initialProgramId, onClose, onCreated }: {
  universityId: string;
  initialProgramId?: string;
  onClose: () => void;
  onCreated: (record: WorkflowInstanceApiRecord) => void;
}) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canAttachProgram = hasPermission(user, 'university.edit');
  const [directionId, setDirectionId] = useState<string | null>(null);
  const [programId, setProgramId] = useState(initialProgramId ?? '');
  const [productId, setProductId] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [serverError, setServerError] = useState<string | null>(null);

  const directionsQuery = useQuery({ queryKey: wizardDirectionsQueryKey, queryFn: ({ signal }) => listWizardDirections(signal), staleTime: 60_000 });
  const universityProgramsQuery = useQuery({
    queryKey: workflowProgramsQueryKey(universityId),
    queryFn: ({ signal }) => getWorkflowSelectorPrograms(universityId, signal),
    staleTime: 30_000,
  });
  const templatesQuery = useQuery({
    queryKey: workflowTemplateListQueryKey(1, 100),
    queryFn: () => listWorkflowTemplates(1, 100),
    staleTime: 30_000,
  });

  const directionOptions = useMemo(() => directionsQuery.data ?? [], [directionsQuery.data]);

  // Каскад без эффектов: выбранное значение действительно, только пока оно есть в опциях.
  const initialDirectionName = universityProgramsQuery.data?.find((program) => program.id === initialProgramId)?.direction;
  const selectedDirectionId = directionId ?? directionOptions.find((direction) => direction.name === initialDirectionName)?.id ?? '';
  const activeDirectionId = directionOptions.some((direction) => direction.id === selectedDirectionId) ? selectedDirectionId : '';

  const catalogProgramsQuery = useQuery({
    queryKey: wizardProgramsQueryKey(activeDirectionId),
    queryFn: ({ signal }) => listWizardPrograms(activeDirectionId, signal),
    enabled: Boolean(activeDirectionId),
    staleTime: 60_000,
  });
  const productsQuery = useQuery({
    queryKey: wizardProductsQueryKey(activeDirectionId),
    queryFn: ({ signal }) => listWizardProducts(activeDirectionId, signal),
    enabled: Boolean(activeDirectionId),
    staleTime: 60_000,
  });

  const programOptions = useMemo(() => {
    const universityPrograms = universityProgramsQuery.data ?? [];
    if (!activeDirectionId) return [];
    const catalog = catalogProgramsQuery.data ?? [];
    const universityIds = new Set(universityPrograms.map((program) => program.id));
    if (catalog.length) {
      const names = new Map(universityPrograms.map((program) => [program.id, program.name]));
      return catalog.filter((program) => canAttachProgram || universityIds.has(program.id)).map((program) => ({
        id: program.id,
        name: names.get(program.id) ?? program.name,
        linked: universityIds.has(program.id),
      }));
    }
    const directionName = directionOptions.find((direction) => direction.id === activeDirectionId)?.name;
    return universityPrograms
      .filter((program) => !directionName || program.direction === directionName)
      .map((program) => ({ id: program.id, name: program.name, linked: true }));
  }, [catalogProgramsQuery.data, activeDirectionId, canAttachProgram, directionOptions, universityProgramsQuery.data]);

  const productOptions = useMemo(() => productsQuery.data ?? [], [productsQuery.data]);
  const templateOptions = useMemo(
    () => (templatesQuery.data?.items ?? []).filter((template) => template.isActive),
    [templatesQuery.data],
  );

  const activeProgramId = programOptions.some((program) => program.id === programId) ? programId : '';
  const activeProductId = productOptions.some((product) => product.id === productId) ? productId : '';
  const activeTemplateId = templateOptions.some((template) => template.id === templateId)
    ? templateId
    : templateOptions.length === 1 ? templateOptions[0].id : '';

  const create = useMutation({
    mutationFn: async () => {
      const linked = programOptions.some((program) => program.id === activeProgramId && program.linked);
      if (!linked) {
        try {
          await attachUniversityProgram(universityId, activeProgramId);
        } catch (cause) {
          // Программа могла быть привязана параллельно — backend вернёт 409, идём дальше.
          if (normalizeApiError(cause).status !== 409) throw cause;
        }
      }
      return createProgramWorkflow(universityId, activeProgramId, activeTemplateId, activeProductId || null);
    },
    onSuccess: async (record) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: universityWorkflowInstancesQueryKey(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowByProgramFamily(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.passport(universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.health(universityId) }),
        queryClient.invalidateQueries({ queryKey: workflowProgramsQueryKey(universityId) }),
      ]);
      onCreated(record);
    },
    onError: (cause) => setServerError(normalizeApiError(cause).message),
  });

  const bootstrapping = directionsQuery.isPending || universityProgramsQuery.isPending;
  const canSubmit = Boolean(activeDirectionId && activeProgramId && activeTemplateId) && !create.isPending;

  return (
    <Modal title="Создание Workflow" onClose={onClose} size="m">
      {bootstrapping ? <SkeletonGroup label="Загрузка данных для создания Workflow"><Skeleton height={220} /></SkeletonGroup> : (
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit) {
              setServerError(null);
              create.mutate();
            }
          }}
        >
          {directionsQuery.isError || universityProgramsQuery.isError ? (
            <FormErrorBanner>
              Не удалось загрузить направления или программы.{' '}
              <Button type="button" variant="ghost" size="s" onClick={() => { void directionsQuery.refetch(); void universityProgramsQuery.refetch(); }}>
                Повторить
              </Button>
            </FormErrorBanner>
          ) : null}

          <div className={styles.field}>
            <SearchableSelect label="ИТ-направление" labelPlacement="outside" value={activeDirectionId} onChange={(value) => { setDirectionId(value); setProgramId(''); setProductId(''); }} options={directionOptions} placeholder="Выберите ИТ-направление" />
            {!directionOptions.length && directionsQuery.isSuccess ? <em>ИТ-направления в каталоге отсутствуют.</em> : null}
          </div>

          <div className={styles.field}>
            <SearchableSelect label="ИТ-программа" labelPlacement="outside" value={activeProgramId} disabled={!activeDirectionId} onChange={(value) => { setProgramId(value); setProductId(''); }} options={programOptions} placeholder="Выберите ИТ-программу" />
            {activeDirectionId && catalogProgramsQuery.isPending ? <em>Загрузка программ…</em> : null}
            {activeDirectionId && !catalogProgramsQuery.isPending && !programOptions.length ? <em>{canAttachProgram ? 'В этом ИТ-направлении пока нет программ в каталоге.' : 'В этом ИТ-направлении нет программ, привязанных к ВУЗу.'}</em> : null}
          </div>

          <div className={styles.field}>
            <SearchableSelect label="ИТ-продукт" labelPlacement="outside" value={activeProductId} disabled={!activeProgramId} onChange={setProductId} options={productOptions.map((product) => ({ id: product.id, name: wizardProductLabel(product) }))} placeholder="Выберите ИТ-продукт (необязательно)" />
            {!activeProgramId ? <em>Сначала выберите ИТ-программу.</em> : null}
            {activeProgramId && productsQuery.isPending ? <em>Загрузка продуктов…</em> : null}
            {activeProgramId && !productsQuery.isPending && !productOptions.length ? <em>В ИТ-направлении пока нет продуктов — ИТ-продукт можно выбрать позже.</em> : null}
          </div>

          <div className={styles.field}>
            <SearchableSelect label="Шаблон Workflow" labelPlacement="outside" value={activeTemplateId} onChange={setTemplateId} options={templateOptions.map((template) => ({ id: template.id, name: template.name }))} placeholder="Выберите шаблон" />
            {templatesQuery.isError ? <em>Не удалось загрузить шаблоны.</em> : null}
            {templatesQuery.isSuccess && !templateOptions.length ? <em>Нет активного шаблона Workflow.</em> : null}
          </div>

          {serverError ? <p role="alert" className={styles.error}>{serverError}</p> : null}

          <div className={styles.actions}>
            <Button type="button" variant="ghost" size="s" onClick={onClose}>
              Отмена
            </Button>
            <Button type="submit" variant="primary" size="s" loading={create.isPending} disabled={!canSubmit}>
              Создать Workflow
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
