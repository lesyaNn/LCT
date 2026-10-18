import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource, isMockDataSourceFor } from './data-source';
import { queryKeys } from './query-keys';
import {
  mockAddWorkflowStage,
  mockCreateWorkflowTemplate,
  mockGetWorkflowTemplate,
  mockListWorkflowTemplates,
  mockUpdateWorkflowStage,
} from '@/shared/mocks/api-adapter';

interface WorkflowTemplateStageApiRecord {
  id: string;
  template_id: string;
  name: string;
  description: string | null;
  order_index: number;
  is_required: boolean;
  is_active: boolean;
  sla_days: number | null;
  default_tasks: string[];
  created_at: string;
  updated_at: string;
}

interface WorkflowTemplateApiRecord {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface WorkflowTemplateDetailApiRecord extends WorkflowTemplateApiRecord {
  stages: WorkflowTemplateStageApiRecord[];
}

interface PaginatedApiResponse<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface WorkflowTemplateStage {
  id: string;
  templateId: string;
  name: string;
  description: string | null;
  orderIndex: number;
  isRequired: boolean;
  isActive: boolean;
  slaDays: number | null;
  defaultTasks: string[];
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowTemplateSummary {
  id: string;
  name: string;
  description: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowTemplate extends WorkflowTemplateSummary {
  stages: WorkflowTemplateStage[];
}

export interface WorkflowTemplatePage {
  items: WorkflowTemplateSummary[];
  page: number;
  pageSize: number;
  total: number;
}

export interface CreateWorkflowTemplateInput {
  name: string;
  description: string | null;
}

export interface UpdateWorkflowTemplateInput {
  name?: string;
  description?: string | null;
  isActive?: boolean;
}

export interface CreateWorkflowStageInput {
  name: string;
  description: string | null;
  isRequired: boolean;
  slaDays: number | null;
  orderIndex?: number;
  defaultTasks?: string[];
}

export interface UpdateWorkflowStageInput {
  name?: string;
  description?: string | null;
  orderIndex?: number;
  isRequired?: boolean;
  isActive?: boolean;
  slaDays?: number | null;
  defaultTasks?: string[];
}

export class WorkflowTemplateApiError extends ApiRequestError {
  constructor(status: number, body: unknown, message: string, transportMessage?: string) {
    super(status, body, message, transportMessage);
    this.name = 'WorkflowTemplateApiError';
  }
}

export const workflowTemplatesQueryKey = queryKeys.workflowTemplates.all;
export const workflowTemplateListsQueryKey = queryKeys.workflowTemplates.lists;
export const workflowTemplateListQueryKey = queryKeys.workflowTemplates.list;
export const workflowTemplateDetailQueryKey = queryKeys.workflowTemplates.detail;

function templateSummaryFromApi(item: WorkflowTemplateApiRecord): WorkflowTemplateSummary {
  return {
    id: item.id,
    name: item.name,
    description: item.description,
    isActive: item.is_active,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
  };
}

function stageFromApi(stage: WorkflowTemplateStageApiRecord): WorkflowTemplateStage {
  return {
    id: stage.id,
    templateId: stage.template_id,
    name: stage.name,
    description: stage.description,
    orderIndex: stage.order_index,
    isRequired: stage.is_required,
    isActive: stage.is_active,
    slaDays: stage.sla_days,
    defaultTasks: stage.default_tasks ?? [],
    createdAt: stage.created_at,
    updatedAt: stage.updated_at,
  };
}

function templateFromApi(item: WorkflowTemplateDetailApiRecord): WorkflowTemplate {
  return {
    ...templateSummaryFromApi(item),
    stages: item.stages.map(stageFromApi).sort((left, right) => left.orderIndex - right.orderIndex),
  };
}

function fail(status: number, body: unknown, error: string, fallback: string): never {
  throw new WorkflowTemplateApiError(status, body, fallback, error);
}

async function listRealWorkflowTemplates(page = 1, pageSize = 100, signal?: AbortSignal): Promise<WorkflowTemplatePage> {
  const result = await apiFetch<PaginatedApiResponse<WorkflowTemplateApiRecord>>(`/api/v1/workflow/templates?page=${page}&page_size=${pageSize}`, { signal });
  if (!result.ok) return fail(result.status, result.body, result.error, 'Не удалось загрузить шаблоны Workflow.');
  return { items: result.data.items.map(templateSummaryFromApi), page: result.data.page, pageSize: result.data.page_size, total: result.data.total };
}

async function getRealWorkflowTemplate(templateId: string, signal?: AbortSignal): Promise<WorkflowTemplate> {
  const result = await apiFetch<WorkflowTemplateDetailApiRecord>(`/api/v1/workflow/templates/${encodeURIComponent(templateId)}`, { signal });
  if (!result.ok) return fail(result.status, result.body, result.error, 'Не удалось загрузить шаблон Workflow.');
  return templateFromApi(result.data);
}

async function createRealWorkflowTemplate(input: CreateWorkflowTemplateInput): Promise<WorkflowTemplate> {
  const result = await apiFetch<WorkflowTemplateDetailApiRecord>('/api/v1/workflow/templates', {
    method: 'POST',
    body: { name: input.name, description: input.description },
  });
  if (!result.ok) return fail(result.status, result.body, result.error, 'Не удалось создать шаблон Workflow.');
  return templateFromApi(result.data);
}

async function updateRealWorkflowTemplate(templateId: string, input: UpdateWorkflowTemplateInput): Promise<WorkflowTemplate> {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.description !== undefined) body.description = input.description;
  if (input.isActive !== undefined) body.is_active = input.isActive;
  const result = await apiFetch<WorkflowTemplateDetailApiRecord>(`/api/v1/workflow/templates/${encodeURIComponent(templateId)}`, { method: 'PATCH', body });
  if (!result.ok) return fail(result.status, result.body, result.error, 'Не удалось изменить шаблон Workflow.');
  return templateFromApi(result.data);
}

async function deleteRealWorkflowTemplate(templateId: string): Promise<void> {
  const result = await apiFetch<{ status: string }>(`/api/v1/workflow/templates/${encodeURIComponent(templateId)}`, { method: 'DELETE' });
  if (!result.ok) return fail(result.status, result.body, result.error, 'Не удалось удалить шаблон Workflow.');
}

async function addRealWorkflowStage(templateId: string, input: CreateWorkflowStageInput): Promise<WorkflowTemplateStage> {
  const result = await apiFetch<WorkflowTemplateStageApiRecord>(`/api/v1/workflow/templates/${encodeURIComponent(templateId)}/stages`, {
    method: 'POST',
    body: {
      name: input.name,
      description: input.description,
      is_required: input.isRequired,
      sla_days: input.slaDays,
      default_tasks: input.defaultTasks ?? [],
      ...(input.orderIndex === undefined ? {} : { order_index: input.orderIndex }),
    },
  });
  if (!result.ok) return fail(result.status, result.body, result.error, 'Не удалось добавить этап.');
  return stageFromApi(result.data);
}

async function updateRealWorkflowStage(templateId: string, stageId: string, input: UpdateWorkflowStageInput): Promise<WorkflowTemplateStage> {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.description !== undefined) body.description = input.description;
  if (input.orderIndex !== undefined) body.order_index = input.orderIndex;
  if (input.isRequired !== undefined) body.is_required = input.isRequired;
  if (input.isActive !== undefined) body.is_active = input.isActive;
  if (input.slaDays !== undefined) body.sla_days = input.slaDays;
  if (input.defaultTasks !== undefined) body.default_tasks = input.defaultTasks;
  const result = await apiFetch<WorkflowTemplateStageApiRecord>(`/api/v1/workflow/templates/${encodeURIComponent(templateId)}/stages/${encodeURIComponent(stageId)}`, { method: 'PATCH', body });
  if (!result.ok) return fail(result.status, result.body, result.error, 'Не удалось сохранить этап.');
  return stageFromApi(result.data);
}

export async function listWorkflowTemplates(page = 1, pageSize = 100, signal?: AbortSignal): Promise<WorkflowTemplatePage> {
  return fromDataSource({
    domain: 'workflow',
    mock: () => mockListWorkflowTemplates(page, pageSize),
    real: () => listRealWorkflowTemplates(page, pageSize, signal),
    signal,
  });
}

export async function getWorkflowTemplate(templateId: string, signal?: AbortSignal): Promise<WorkflowTemplate> {
  return fromDataSource({
    domain: 'workflow',
    mock: () => mockGetWorkflowTemplate(templateId),
    real: () => getRealWorkflowTemplate(templateId, signal),
    signal,
  });
}

export async function createWorkflowTemplate(input: CreateWorkflowTemplateInput): Promise<WorkflowTemplate> {
  return fromDataSource({ domain: 'workflow', mock: () => mockCreateWorkflowTemplate(input), real: () => createRealWorkflowTemplate(input) });
}

export async function updateWorkflowTemplate(templateId: string, input: UpdateWorkflowTemplateInput): Promise<WorkflowTemplate> {
  if (isMockDataSourceFor('workflow')) throw new WorkflowTemplateApiError(0, undefined, 'Изменение статуса шаблона недоступно в деморежиме.');
  return updateRealWorkflowTemplate(templateId, input);
}

export async function deleteWorkflowTemplate(templateId: string): Promise<void> {
  if (isMockDataSourceFor('workflow')) throw new WorkflowTemplateApiError(0, undefined, 'Удаление шаблона недоступно в демонстрационном режиме.');
  return deleteRealWorkflowTemplate(templateId);
}

export async function addWorkflowStage(templateId: string, input: CreateWorkflowStageInput): Promise<WorkflowTemplateStage> {
  return fromDataSource({ domain: 'workflow', mock: () => mockAddWorkflowStage(templateId, input), real: () => addRealWorkflowStage(templateId, input) });
}

export async function updateWorkflowStage(templateId: string, stageId: string, input: UpdateWorkflowStageInput): Promise<WorkflowTemplateStage> {
  return fromDataSource({ domain: 'workflow', mock: () => mockUpdateWorkflowStage(templateId, stageId, input), real: () => updateRealWorkflowStage(templateId, stageId, input) });
}
