'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getWorkflowStageOrderMoves, insertWorkflowStage, moveWorkflowStage, normalizeWorkflowStageOrder, patchWorkflowStage } from './workflow-template-cache';
import {
  addWorkflowStage,
  createWorkflowTemplate,
  deleteWorkflowTemplate,
  updateWorkflowTemplate,
  updateWorkflowStage,
  workflowTemplateDetailQueryKey,
  workflowTemplateListsQueryKey,
  type CreateWorkflowStageInput,
  type CreateWorkflowTemplateInput,
  type UpdateWorkflowTemplateInput,
  type UpdateWorkflowStageInput,
  type WorkflowTemplate,
  type WorkflowTemplateStage,
} from './workflow-templates-repository';

export function useCreateWorkflowTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateWorkflowTemplateInput) => createWorkflowTemplate(input),
    onSuccess: async (template) => {
      queryClient.setQueryData(workflowTemplateDetailQueryKey(template.id), template);
      await queryClient.invalidateQueries({ queryKey: workflowTemplateListsQueryKey });
    },
  });
}

export function useUpdateWorkflowTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, patch }: { templateId: string; patch: UpdateWorkflowTemplateInput }) => updateWorkflowTemplate(templateId, patch),
    onSuccess: async (template) => {
      queryClient.setQueryData(workflowTemplateDetailQueryKey(template.id), template);
      await queryClient.invalidateQueries({ queryKey: workflowTemplateListsQueryKey });
    },
  });
}

export function useDeleteWorkflowTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteWorkflowTemplate,
    onSuccess: async (_data, templateId) => {
      queryClient.removeQueries({ queryKey: workflowTemplateDetailQueryKey(templateId) });
      await queryClient.invalidateQueries({ queryKey: workflowTemplateListsQueryKey });
    },
  });
}

export function useAddWorkflowStage(templateId: string) {
  const queryClient = useQueryClient();
  const detailKey = workflowTemplateDetailQueryKey(templateId);
  return useMutation<WorkflowTemplateStage, Error, CreateWorkflowStageInput, { previous?: WorkflowTemplate; temporaryId: string }>({
    mutationFn: (input: CreateWorkflowStageInput) => addWorkflowStage(templateId, input),
    onMutate: async (input) => {
      await queryClient.cancelQueries({ queryKey: detailKey });
      const previous = queryClient.getQueryData<WorkflowTemplate>(detailKey);
      const temporaryId = `temp:stage:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`;
      if (previous) {
        const now = new Date().toISOString();
        const orderIndex = input.orderIndex ?? previous.stages.length + 1;
        const temporaryStage: WorkflowTemplateStage = {
          id: temporaryId,
          templateId,
          name: input.name,
          description: input.description,
          orderIndex,
          isRequired: input.isRequired,
          isActive: true,
          slaDays: input.slaDays,
          createdAt: now,
          updatedAt: now,
        };
        queryClient.setQueryData<WorkflowTemplate>(detailKey, {
          ...previous,
          stages: insertWorkflowStage(previous.stages, temporaryStage, orderIndex),
        });
      }
      return { previous, temporaryId };
    },
    onError: (_error, _input, context) => {
      if (context?.previous) queryClient.setQueryData(detailKey, context.previous);
    },
    onSuccess: (stage, _input, context) => {
      queryClient.setQueryData<WorkflowTemplate>(detailKey, (current) => current ? {
        ...current,
        stages: normalizeWorkflowStageOrder(current.stages.map((item) => item.id === context.temporaryId ? stage : item)),
      } : current);
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: detailKey, exact: true });
    },
  });
}

interface UpdateStageVariables {
  stageId: string;
  patch: UpdateWorkflowStageInput;
}

export function useUpdateWorkflowStage(templateId: string) {
  const queryClient = useQueryClient();
  const detailKey = workflowTemplateDetailQueryKey(templateId);
  return useMutation<WorkflowTemplateStage, Error, UpdateStageVariables, { previous?: WorkflowTemplate }>({
    mutationFn: ({ stageId, patch }) => updateWorkflowStage(templateId, stageId, patch),
    onMutate: async ({ stageId, patch }) => {
      await queryClient.cancelQueries({ queryKey: detailKey });
      const previous = queryClient.getQueryData<WorkflowTemplate>(detailKey);
      const optimisticPatch: Partial<WorkflowTemplateStage> = {};
      if (patch.name !== undefined) optimisticPatch.name = patch.name;
      if (patch.description !== undefined) optimisticPatch.description = patch.description;
      if (patch.orderIndex !== undefined) optimisticPatch.orderIndex = patch.orderIndex;
      if (patch.isRequired !== undefined) optimisticPatch.isRequired = patch.isRequired;
      if (patch.isActive !== undefined) optimisticPatch.isActive = patch.isActive;
      if (patch.slaDays !== undefined) optimisticPatch.slaDays = patch.slaDays;
      queryClient.setQueryData<WorkflowTemplate>(detailKey, (current) => patchWorkflowStage(current, stageId, optimisticPatch));
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(detailKey, context.previous);
    },
    onSuccess: (stage) => {
      queryClient.setQueryData<WorkflowTemplate>(detailKey, (current) => patchWorkflowStage(current, stage.id, stage));
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: detailKey, exact: true, refetchType: 'none' });
    },
  });
}

interface SaveOrderVariables {
  previousStages: WorkflowTemplateStage[];
  targetStages: WorkflowTemplateStage[];
}

export function useSaveWorkflowStageOrder(templateId: string) {
  const queryClient = useQueryClient();
  const detailKey = workflowTemplateDetailQueryKey(templateId);
  return useMutation<void, Error, SaveOrderVariables, { rollback?: WorkflowTemplate }>({
    mutationFn: async ({ previousStages, targetStages }) => {
      const moves = getWorkflowStageOrderMoves(previousStages, targetStages);
      let serverOrder = [...previousStages];
      try {
        for (const move of moves) {
          await updateWorkflowStage(templateId, move.stageId, { orderIndex: move.orderIndex });
          const fromIndex = serverOrder.findIndex((stage) => stage.id === move.stageId);
          serverOrder = moveWorkflowStage(serverOrder, fromIndex, move.orderIndex - 1);
        }
      } catch (cause) {
        const rollbackMoves = getWorkflowStageOrderMoves(serverOrder, previousStages);
        for (const rollback of rollbackMoves) {
          try {
            await updateWorkflowStage(templateId, rollback.stageId, { orderIndex: rollback.orderIndex });
            const fromIndex = serverOrder.findIndex((stage) => stage.id === rollback.stageId);
            serverOrder = moveWorkflowStage(serverOrder, fromIndex, rollback.orderIndex - 1);
          } catch {
            break;
          }
        }
        throw cause;
      }
    },
    onMutate: async ({ previousStages, targetStages }) => {
      await queryClient.cancelQueries({ queryKey: detailKey });
      const current = queryClient.getQueryData<WorkflowTemplate>(detailKey);
      const rollback = current ? { ...current, stages: previousStages } : undefined;
      if (current) queryClient.setQueryData<WorkflowTemplate>(detailKey, { ...current, stages: targetStages });
      return { rollback };
    },
    onError: (_error, _variables, context) => {
      if (context?.rollback) queryClient.setQueryData(detailKey, context.rollback);
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: detailKey, exact: true });
    },
  });
}
