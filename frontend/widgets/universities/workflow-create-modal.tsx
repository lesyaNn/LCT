'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { Select } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { Skeleton, SkeletonGroup } from '@/shared/ui/skeleton';
import styles from './workflow-transition-modal.module.css';

export function WorkflowCreateModal({ universityId, onClose, onCreated }: {
  universityId: string;
  onClose: () => void;
  onCreated: (record: WorkflowInstanceApiRecord) => void;
}) {
  const queryClient = useQueryClient();
  const [directionId, setDirectionId] = useState('');
  const [programId, setProgramId] = useState('');
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
  const activeDirectionId = directionOptions.some((direction) => direction.id === directionId) ? directionId : '';

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
      return catalog.map((program) => ({
        id: program.id,
        name: names.get(program.id) ?? program.name,
        linked: universityIds.has(program.id),
      }));
    }
    const directionName = directionOptions.find((direction) => direction.id === activeDirectionId)?.name;
    return universityPrograms
      .filter((program) => !directionName || program.direction === directionName)
      .map((program) => ({ id: program.id, name: program.name, linked: true }));
  }, [catalogProgramsQuery.data, activeDirectionId, directionOptions, universityProgramsQuery.data]);

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
        queryClient.invalidateQueries({ queryKey: workflowProgramsQueryKey(universityId) }),
      ]);
      onCreated(record);
    },
    onError: (cause) => setServerError(normalizeApiError(cause).message),
  });

  const bootstrapping = directionsQuery.isPending || universityProgramsQuery.isPending;
  const canSubmit = Boolean(activeDirectionId && activeProgramId && activeTemplateId) && !create.isPending;

  return (
    <Modal title="Создание воркфлоу" onClose={onClose} size="m">
      {bootstrapping ? <SkeletonGroup label="Загрузка данных для создания воркфлоу"><Skeleton height={220} /></SkeletonGroup> : (
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

          <label className={styles.field}>
            <span>Направление</span>
            <Select
              value={activeDirectionId}
              onChange={(event) => { setDirectionId(event.target.value); setProgramId(''); setProductId(''); }}
            >
              <option value="">Выберите направление</option>
              {directionOptions.map((direction) => (
                <option key={direction.id} value={direction.id}>
                  {direction.name}
                </option>
              ))}
            </Select>
            {!directionOptions.length && directionsQuery.isSuccess ? <em>Направления в каталоге отсутствуют.</em> : null}
          </label>

          <label className={styles.field}>
            <span>Программа обучения</span>
            <Select value={activeProgramId} disabled={!activeDirectionId} onChange={(event) => setProgramId(event.target.value)}>
              <option value="">Выберите программу</option>
              {programOptions.map((program) => (
                <option key={program.id} value={program.id}>
                  {program.name}
                </option>
              ))}
            </Select>
            {activeDirectionId && catalogProgramsQuery.isPending ? <em>Загрузка программ…</em> : null}
            {activeDirectionId && !catalogProgramsQuery.isPending && !programOptions.length ? (
              <em>В этом направлении пока нет программ в каталоге.</em>
            ) : null}
          </label>

          <label className={styles.field}>
            <span>Продукт</span>
            <Select value={activeProductId} disabled={!activeDirectionId} onChange={(event) => setProductId(event.target.value)}>
              <option value="">Выберите продукт (необязательно)</option>
              {productOptions.map((product) => (
                <option key={product.id} value={product.id}>
                  {wizardProductLabel(product)}
                </option>
              ))}
            </Select>
            {activeDirectionId && productsQuery.isPending ? <em>Загрузка продуктов…</em> : null}
            {activeDirectionId && !productsQuery.isPending && !productOptions.length ? (
              <em>В направлении пока нет продуктов — продукт можно выбрать позже.</em>
            ) : null}
            <em>Продукт выбирается на перспективу: на него планируется получить лицензию, наличие лицензии не требуется.</em>
          </label>

          <label className={styles.field}>
            <span>Шаблон воркфлоу</span>
            <Select value={activeTemplateId} onChange={(event) => setTemplateId(event.target.value)}>
              <option value="">Выберите шаблон</option>
              {templateOptions.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </Select>
            {templatesQuery.isError ? <em>Не удалось загрузить шаблоны.</em> : null}
            {templatesQuery.isSuccess && !templateOptions.length ? <em>Нет активного шаблона воркфлоу.</em> : null}
          </label>

          {serverError ? <p role="alert" className={styles.error}>{serverError}</p> : null}

          <div className={styles.actions}>
            <Button type="button" variant="ghost" size="s" onClick={onClose}>
              Отмена
            </Button>
            <Button type="submit" variant="primary" size="s" loading={create.isPending} disabled={!canSubmit}>
              Создать воркфлоу
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
