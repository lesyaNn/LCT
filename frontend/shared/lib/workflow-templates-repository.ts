import { apiFetch } from './api-client';

interface WorkflowTemplateStageApiRecord {
  id: string;
  template_id: string;
  name: string;
  description: string | null;
  order_index: number;
  is_required: boolean;
  is_active: boolean;
  sla_days: number | null;
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

export interface CreateWorkflowStageInput {
  name: string;
  description: string | null;
  isRequired: boolean;
  slaDays: number | null;
  orderIndex?: number;
}

export interface UpdateWorkflowStageInput {
  name?: string;
  description?: string | null;
  orderIndex?: number;
  isRequired?: boolean;
  isActive?: boolean;
  slaDays?: number | null;
}

export class WorkflowTemplateApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'WorkflowTemplateApiError';
  }
}

export const workflowTemplatesQueryKey = ['workflow-templates'] as const;
export const workflowTemplateListsQueryKey = [...workflowTemplatesQueryKey, 'list'] as const;
export const workflowTemplateListQueryKey = (page = 1, pageSize = 100) => [...workflowTemplatesQueryKey, 'list', page, pageSize] as const;
export const workflowTemplateDetailQueryKey = (templateId: string) => [...workflowTemplatesQueryKey, 'detail', templateId] as const;

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

function messageForError(error: string, fallback: string): string {
  if (error.includes('Workflow template not found')) return 'Шаблон Workflow не найден.';
  if (error.includes('Workflow stage not found')) return 'Этап Workflow не найден.';
  if (error.startsWith('403')) return 'Недостаточно прав для управления шаблонами.';
  if (error.startsWith('409') || error.includes('uq_workflow_templates_name')) return 'Шаблон с таким названием уже существует.';
  return fallback;
}

function fail(status: number, error: string, fallback: string): never {
  throw new WorkflowTemplateApiError(messageForError(error, fallback), status);
}

export async function listWorkflowTemplates(page = 1, pageSize = 100, signal?: AbortSignal): Promise<WorkflowTemplatePage> {
  const result = await apiFetch<PaginatedApiResponse<WorkflowTemplateApiRecord>>(`/api/v1/workflow/templates?page=${page}&page_size=${pageSize}`, { signal });
  if (!result.ok) return fail(result.status, result.error, 'Не удалось загрузить шаблоны Workflow.');
  return { items: result.data.items.map(templateSummaryFromApi), page: result.data.page, pageSize: result.data.page_size, total: result.data.total };
}

export async function getWorkflowTemplate(templateId: string, signal?: AbortSignal): Promise<WorkflowTemplate> {
  const result = await apiFetch<WorkflowTemplateDetailApiRecord>(`/api/v1/workflow/templates/${encodeURIComponent(templateId)}`, { signal });
  if (!result.ok) return fail(result.status, result.error, 'Не удалось загрузить шаблон Workflow.');
  return templateFromApi(result.data);
}

export async function createWorkflowTemplate(input: CreateWorkflowTemplateInput): Promise<WorkflowTemplate> {
  const result = await apiFetch<WorkflowTemplateDetailApiRecord>('/api/v1/workflow/templates', {
    method: 'POST',
    body: { name: input.name, description: input.description },
  });
  if (!result.ok) return fail(result.status, result.error, 'Не удалось создать шаблон Workflow.');
  return templateFromApi(result.data);
}

export async function addWorkflowStage(templateId: string, input: CreateWorkflowStageInput): Promise<WorkflowTemplateStage> {
  const result = await apiFetch<WorkflowTemplateStageApiRecord>(`/api/v1/workflow/templates/${encodeURIComponent(templateId)}/stages`, {
    method: 'POST',
    body: {
      name: input.name,
      description: input.description,
      is_required: input.isRequired,
      sla_days: input.slaDays,
      ...(input.orderIndex === undefined ? {} : { order_index: input.orderIndex }),
    },
  });
  if (!result.ok) return fail(result.status, result.error, 'Не удалось добавить этап.');
  return stageFromApi(result.data);
}

export async function updateWorkflowStage(templateId: string, stageId: string, input: UpdateWorkflowStageInput): Promise<WorkflowTemplateStage> {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.description !== undefined) body.description = input.description;
  if (input.orderIndex !== undefined) body.order_index = input.orderIndex;
  if (input.isRequired !== undefined) body.is_required = input.isRequired;
  if (input.isActive !== undefined) body.is_active = input.isActive;
  if (input.slaDays !== undefined) body.sla_days = input.slaDays;
  const result = await apiFetch<WorkflowTemplateStageApiRecord>(`/api/v1/workflow/templates/${encodeURIComponent(templateId)}/stages/${encodeURIComponent(stageId)}`, { method: 'PATCH', body });
  if (!result.ok) return fail(result.status, result.error, 'Не удалось сохранить этап.');
  return stageFromApi(result.data);
}
