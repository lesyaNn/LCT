import type { AuditEvent, AuditListQuery, AuditListResult } from '@/shared/lib/audit-repository';
import type { ImportCatalogType, ImportExecuteResponse, ImportJob, ImportOptions, ImportPreviewResponse } from '@/shared/lib/import-repository';
import type { ReportJob, ReportRequest } from '@/shared/lib/reports-repository';
import type {
  WorkflowCommentApiRecord,
  WorkflowInstanceApiRecord,
  WorkflowInstanceApiStage,
} from '@/shared/lib/universities-repository';
import type {
  CreateWorkflowStageInput,
  CreateWorkflowTemplateInput,
  UpdateWorkflowStageInput,
  WorkflowTemplate,
  WorkflowTemplatePage,
  WorkflowTemplateStage,
} from '@/shared/lib/workflow-templates-repository';

function id(prefix: string): string {
  const suffix = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefix}-${suffix}`;
}

function now(): string {
  return new Date().toISOString();
}

const storagePrefix = 'rtk.mock-api.v1:';

function readSession<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const value = window.sessionStorage.getItem(`${storagePrefix}${key}`);
    return value ? JSON.parse(value) as T : fallback;
  } catch {
    return fallback;
  }
}

function writeSession<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return;
  try { window.sessionStorage.setItem(`${storagePrefix}${key}`, JSON.stringify(value)); } catch { /* storage is optional */ }
}

// ---------------------------------------------------------------- workflow

type MockWorkflowStageDefinition = {
  id: string;
  name: string;
  orderIndex: number;
  isRequired: boolean;
};

type MockWorkflowDefinition = {
  instanceId: string;
  universityId: string;
  universityName: string;
  currentStageId: string;
  stages: MockWorkflowStageDefinition[];
};

const workflowDefinitions = new Map<string, MockWorkflowDefinition>();
const workflowComments = new Map<string, WorkflowCommentApiRecord[]>();

export function registerMockWorkflow(input: {
  instanceId: string;
  universityId: string;
  universityName: string;
  currentStageId: string;
  stages: MockWorkflowStageDefinition[];
}): void {
  const current = workflowDefinitions.get(input.instanceId);
  const storedStageId = readSession<string | null>(`workflow-stage:${input.instanceId}`, null);
  workflowDefinitions.set(input.instanceId, {
    ...input,
    currentStageId: current?.currentStageId ?? storedStageId ?? input.currentStageId,
  });
}

export function getMockWorkflowCurrentStageId(instanceId: string): string | undefined {
  return workflowDefinitions.get(instanceId)?.currentStageId
    ?? readSession<string | null>(`workflow-stage:${instanceId}`, null)
    ?? undefined;
}

function defaultWorkflow(instanceId: string): MockWorkflowDefinition {
  const stages = ['Инициация проекта', 'Сбор данных о вузе', 'Подготовка дорожной карты', 'Согласование программы', 'Пилотный запуск', 'Сопровождение запуска']
    .map((name, index) => ({ id: `${instanceId}-workflow-stage-${index + 1}`, name, orderIndex: index + 1, isRequired: true }));
  return {
    instanceId,
    universityId: instanceId,
    universityName: 'Демонстрационный университет',
    currentStageId: stages[2].id,
    stages,
  };
}

function workflowDefinition(instanceId: string): MockWorkflowDefinition {
  const existing = workflowDefinitions.get(instanceId);
  if (existing) return existing;
  const created = defaultWorkflow(instanceId);
  workflowDefinitions.set(instanceId, created);
  return created;
}

function workflowRecord(definition: MockWorkflowDefinition): WorkflowInstanceApiRecord {
  const currentIndex = definition.stages.findIndex((stage) => stage.id === definition.currentStageId);
  const stages: WorkflowInstanceApiStage[] = definition.stages.map((stage, index) => ({
    id: stage.id,
    template_stage_id: `template-${stage.id}`,
    order_index: stage.orderIndex,
    name: stage.name,
    description: null,
    is_required: stage.isRequired,
    status: index < currentIndex ? 'completed' : 'pending',
    due_date: index === currentIndex ? '2026-10-15' : null,
    completed_at: index < currentIndex ? '2026-09-20T12:00:00.000Z' : null,
    is_overdue: false,
    days_overdue: 0,
  }));
  return {
    id: definition.instanceId,
    university_id: definition.universityId,
    template_id: 'mock-template-main',
    current_stage_id: stages[currentIndex]?.template_stage_id ?? null,
    current_instance_stage_id: definition.currentStageId,
    responsible_id: 'responsible-anna',
    status: currentIndex >= stages.length - 1 ? 'completed' : 'active',
    due_date: stages[currentIndex]?.due_date ?? null,
    completed_at: currentIndex >= stages.length - 1 ? now() : null,
    is_overdue: false,
    days_overdue: 0,
    stages,
  };
}

export function mockGetWorkflowInstance(instanceId: string): WorkflowInstanceApiRecord {
  return workflowRecord(workflowDefinition(instanceId));
}

export function mockTransitionWorkflow(instanceId: string, targetStageId: string, comment: string): WorkflowInstanceApiRecord {
  const definition = workflowDefinition(instanceId);
  const currentIndex = definition.stages.findIndex((stage) => stage.id === definition.currentStageId);
  const targetIndex = definition.stages.findIndex((stage) => stage.id === targetStageId);
  if (targetIndex <= currentIndex) throw new Error('Можно перейти только на следующий доступный этап.');
  const target = definition.stages[targetIndex];
  const previous = definition.stages[currentIndex];
  definition.currentStageId = target.id;
  workflowDefinitions.set(instanceId, definition);
  writeSession(`workflow-stage:${instanceId}`, target.id);
  prependAuditEvent({
    id: id('audit-transition'),
    occurredAt: now(),
    user: { id: 'mock-manager', name: 'Мария Менеджер', email: 'manager@example.test' },
    role: 'manager',
    action: 'WORKFLOW_TRANSITION',
    entity: { id: instanceId, type: 'workflow_instance', label: definition.universityName },
    university: { id: definition.universityId, name: definition.universityName },
    oldValues: { stage: previous?.name ?? '—' },
    newValues: { stage: target.name, comment },
    requestId: id('request'),
  });
  return workflowRecord(definition);
}

export function mockListWorkflowComments(instanceId: string): WorkflowCommentApiRecord[] {
  const comments = workflowComments.get(instanceId)
    ?? readSession<WorkflowCommentApiRecord[]>(`workflow-comments:${instanceId}`, []);
  workflowComments.set(instanceId, comments);
  return [...comments];
}

export function mockCreateWorkflowComment(instanceId: string, content: string, stageId?: string): WorkflowCommentApiRecord {
  workflowDefinition(instanceId);
  const timestamp = now();
  const comment: WorkflowCommentApiRecord = {
    id: id('comment'),
    instance_id: instanceId,
    stage_id: stageId ?? null,
    author_keycloak_sub: 'mock-manager',
    content,
    is_internal: false,
    created_at: timestamp,
    updated_at: timestamp,
  };
  const comments = [...mockListWorkflowComments(instanceId), comment];
  workflowComments.set(instanceId, comments);
  writeSession(`workflow-comments:${instanceId}`, comments);
  return comment;
}

export function mockEditWorkflowComment(commentId: string, content: string): WorkflowCommentApiRecord {
  for (const [instanceId, comments] of workflowComments) {
    const index = comments.findIndex((comment) => comment.id === commentId);
    if (index < 0) continue;
    const updated = { ...comments[index], content, updated_at: now() };
    const next = [...comments];
    next[index] = updated;
    workflowComments.set(instanceId, next);
    writeSession(`workflow-comments:${instanceId}`, next);
    return updated;
  }
  throw new Error('Комментарий не найден.');
}

// ---------------------------------------------------------------- reports

type StoredReportJob = ReportJob & { readyAt: number; buildingAt: number };
const reportJobs = new Map<string, StoredReportJob>();
const mockXlsxDataUrl = 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,UEsDBAoAAAAAAAEAIQAAAAAAAAAAAAAAAAAJAAAAd29ya2Jvb2svUEsBAhQACgAAAAAAAQAhAAAAAAAAAAAAAAAAAAkAAAAAAAAAAAAAAAAAAAAAAHdvcmtib29rL1BLBQYAAAAAAQABADcAAAAnAAAAAAA=';

function visibleReportJob(stored: StoredReportJob): ReportJob {
  const timestamp = Date.now();
  const status = timestamp >= stored.readyAt ? 'ready' : timestamp >= stored.buildingAt ? 'building' : 'queued';
  const progress = status === 'ready' ? 100 : status === 'building' ? 64 : 0;
  return {
    ...stored,
    status,
    progress,
    downloadUrl: status === 'ready' ? mockXlsxDataUrl : undefined,
  };
}

export function mockCreateReportJob(request: ReportRequest): ReportJob {
  const createdAt = now();
  const created = Date.now();
  const job: StoredReportJob = {
    id: id('report'),
    name: `Экспорт ${request.format.toUpperCase()}`,
    format: request.format,
    status: 'queued',
    progress: 0,
    createdAt,
    request,
    buildingAt: created + 1_000,
    readyAt: created + 4_500,
  };
  reportJobs.set(job.id, job);
  return visibleReportJob(job);
}

export function mockGetReportJob(jobId: string): ReportJob {
  const job = reportJobs.get(jobId);
  if (!job) throw new Error('Задача отчёта не найдена.');
  return visibleReportJob(job);
}

export function mockListReportJobs(): ReportJob[] {
  return [...reportJobs.values()]
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .map(visibleReportJob);
}

// ------------------------------------------------------------------- audit

const seededAuditEvents: AuditEvent[] = [
  {
    id: 'audit-demo-001',
    occurredAt: '2026-09-23T09:35:00.000Z',
    user: { id: 'mock-manager', name: 'Мария Менеджер', email: 'manager@example.test' },
    role: 'manager',
    action: 'UPDATE',
    entity: { id: 'university-001', type: 'university', label: 'МТУСИ' },
    university: { id: 'university-001', name: 'Московский технический университет связи и информатики' },
    oldValues: { status: 'Подготовка' },
    newValues: { status: 'Запуск' },
  },
  {
    id: 'audit-demo-002',
    occurredAt: '2026-09-22T13:10:00.000Z',
    user: { id: 'mock-curator', name: 'Анна Иванова', email: 'curator@example.test' },
    role: 'curator',
    action: 'CREATE',
    entity: { id: 'document-001', type: 'document', label: 'Дорожная карта' },
    university: { id: 'university-001', name: 'Московский технический университет связи и информатики' },
    newValues: { file_name: 'дорожная-карта.pdf' },
  },
];

function prependAuditEvent(event: AuditEvent): void {
  writeSession('audit-events', [event, ...readSession<AuditEvent[]>('audit-events', [])]);
}

export function mockGetAuditEvents(query: AuditListQuery): AuditListResult {
  const auditEvents = [...readSession<AuditEvent[]>('audit-events', []), ...seededAuditEvents];
  const { filters } = query;
  const filtered = auditEvents.filter((event) => {
    const date = event.occurredAt.slice(0, 10);
    if (filters.dateFrom && date < filters.dateFrom) return false;
    if (filters.dateTo && date > filters.dateTo) return false;
    if (filters.userIds.length && !filters.userIds.includes(event.user.id)) return false;
    if (filters.universityIds.length && !filters.universityIds.includes(event.university.id)) return false;
    if (filters.actions.length && !filters.actions.includes(event.action)) return false;
    if (filters.entityTypes.length && !filters.entityTypes.includes(event.entity.type)) return false;
    return true;
  });
  const start = (query.page - 1) * query.pageSize;
  return {
    items: filtered.slice(start, start + query.pageSize),
    total: filtered.length,
    page: query.page,
    pageSize: query.pageSize,
    filterOptions: {
      users: [...new Map(auditEvents.map((event) => [event.user.id, event.user])).values()].map(({ id: userId, name }) => ({ id: userId, name })),
      universities: [...new Map(auditEvents.map((event) => [event.university.id, event.university])).values()],
      actions: [...new Set(auditEvents.map((event) => event.action))],
      entityTypes: [...new Set(auditEvents.map((event) => event.entity.type))],
    },
    capabilities: { dateRange: true, users: true, universities: true, actions: true, entityTypes: true, pagination: true },
  };
}

// ------------------------------------------------------- workflow templates

const templateTimestamp = '2026-09-20T09:00:00.000Z';
const workflowTemplates = new Map<string, WorkflowTemplate>([
  ['mock-template-main', {
    id: 'mock-template-main',
    name: 'Подключение университета',
    description: 'Основной демонстрационный процесс подключения.',
    isActive: true,
    createdAt: templateTimestamp,
    updatedAt: templateTimestamp,
    stages: ['Инициация', 'Сбор данных', 'Дорожная карта', 'Согласование', 'Пилотный запуск'].map((name, index) => ({
      id: `mock-template-main-stage-${index + 1}`,
      templateId: 'mock-template-main',
      name,
      description: null,
      orderIndex: index + 1,
      isRequired: index !== 2,
      isActive: true,
      slaDays: 5 + index,
      createdAt: templateTimestamp,
      updatedAt: templateTimestamp,
    })),
  }],
]);

function cloneTemplate(template: WorkflowTemplate): WorkflowTemplate {
  return { ...template, stages: template.stages.map((stage) => ({ ...stage })) };
}

export function mockListWorkflowTemplates(page: number, pageSize: number): WorkflowTemplatePage {
  const templates = [...workflowTemplates.values()];
  const start = (page - 1) * pageSize;
  return {
    items: templates.slice(start, start + pageSize).map((template) => ({
      id: template.id,
      name: template.name,
      description: template.description,
      isActive: template.isActive,
      createdAt: template.createdAt,
      updatedAt: template.updatedAt,
    })),
    page,
    pageSize,
    total: templates.length,
  };
}

export function mockGetWorkflowTemplate(templateId: string): WorkflowTemplate {
  const template = workflowTemplates.get(templateId);
  if (!template) throw new Error('Шаблон Workflow не найден.');
  return cloneTemplate(template);
}

export function mockCreateWorkflowTemplate(input: CreateWorkflowTemplateInput): WorkflowTemplate {
  const timestamp = now();
  const template: WorkflowTemplate = {
    id: id('template'),
    name: input.name,
    description: input.description,
    isActive: true,
    createdAt: timestamp,
    updatedAt: timestamp,
    stages: [],
  };
  workflowTemplates.set(template.id, template);
  return cloneTemplate(template);
}

export function mockAddWorkflowStage(templateId: string, input: CreateWorkflowStageInput): WorkflowTemplateStage {
  const template = workflowTemplates.get(templateId);
  if (!template) throw new Error('Шаблон Workflow не найден.');
  const timestamp = now();
  const stage: WorkflowTemplateStage = {
    id: id('stage'),
    templateId,
    name: input.name,
    description: input.description,
    orderIndex: input.orderIndex ?? template.stages.length + 1,
    isRequired: input.isRequired,
    isActive: true,
    slaDays: input.slaDays,
    createdAt: timestamp,
    updatedAt: timestamp,
  };
  template.stages.push(stage);
  template.stages.sort((left, right) => left.orderIndex - right.orderIndex).forEach((item, index) => { item.orderIndex = index + 1; });
  template.updatedAt = timestamp;
  return { ...stage };
}

export function mockUpdateWorkflowStage(templateId: string, stageId: string, input: UpdateWorkflowStageInput): WorkflowTemplateStage {
  const template = workflowTemplates.get(templateId);
  const stage = template?.stages.find((item) => item.id === stageId);
  if (!template || !stage) throw new Error('Этап Workflow не найден.');
  Object.assign(stage, {
    ...(input.name === undefined ? {} : { name: input.name }),
    ...(input.description === undefined ? {} : { description: input.description }),
    ...(input.isRequired === undefined ? {} : { isRequired: input.isRequired }),
    ...(input.isActive === undefined ? {} : { isActive: input.isActive }),
    ...(input.slaDays === undefined ? {} : { slaDays: input.slaDays }),
    updatedAt: now(),
  });
  if (input.orderIndex !== undefined) {
    const without = template.stages.filter((item) => item.id !== stageId);
    without.splice(Math.max(0, Math.min(without.length, input.orderIndex - 1)), 0, stage);
    template.stages = without.map((item, index) => ({ ...item, orderIndex: index + 1 }));
  }
  template.updatedAt = now();
  return { ...(template.stages.find((item) => item.id === stageId) ?? stage) };
}

// --------------------------------------------------------------------- import

type StoredImportFile = { filename: string; catalogType?: ImportCatalogType };
type StoredImportJob = ImportJob & { processingAt: number; doneAt: number; options: ImportOptions };

const importFiles = new Map<string, StoredImportFile>();
const importJobs = new Map<string, StoredImportJob>();

const importPreviewHeaders = ['Название ВУЗа', 'Номер договора', 'Срок действия лицензии (год)', 'Вендор', 'ПО'];
const importPreviewRows = [
  { 'Название ВУЗа': 'МТУСИ', 'Номер договора': 'ДОГ-2026-001', 'Срок действия лицензии (год)': 2027, Вендор: 'Ростелеком', ПО: 'Профессиональная переподготовка' },
  { 'Название ВУЗа': 'Уральский федеральный университет', 'Номер договора': 'ДОГ-2026-002', 'Срок действия лицензии (год)': 2028, Вендор: 'Контур', ПО: 'Короткие курсы' },
  { 'Название ВУЗа': 'Казанский федеральный университет', 'Номер договора': 'ДОГ-2026-003', 'Срок действия лицензии (год)': 2027, Вендор: 'Ростелеком', ПО: 'Корпоративный трек' },
];

export function mockUploadImportPreview(file: File): ImportPreviewResponse {
  const fileId = id('import-file');
  importFiles.set(fileId, { filename: file.name });
  return {
    file_id: fileId,
    filename: file.name,
    headers: [...importPreviewHeaders],
    preview: importPreviewRows.map((row) => ({ ...row })),
    row_count: 20,
    detected_sheet: 'Лист1',
  };
}

function visibleImportJob(stored: StoredImportJob): Record<string, unknown> {
  const timestamp = Date.now();
  const status = timestamp >= stored.doneAt ? 'done' : timestamp >= stored.processingAt ? 'processing' : 'queued';
  return {
    id: stored.id,
    type: stored.type,
    status,
    created_at: stored.createdAt,
    filename: stored.filename,
    catalog_type: stored.catalogType,
    created_by: stored.createdBy,
    result: status === 'done' ? stored.result : undefined,
  };
}

export function mockExecuteImport(fileId: string, _mapping: Record<string, string>, options: ImportOptions): ImportExecuteResponse {
  const file = importFiles.get(fileId);
  if (!file) throw new Error('Файл импорта не найден. Загрузите его заново.');
  const created = Date.now();
  const job: StoredImportJob = {
    id: id('import-job'),
    type: 'xlsx_import',
    status: 'queued',
    createdAt: now(),
    filename: file.filename,
    catalogType: file.catalogType,
    createdBy: 'Мария Менеджер',
    processingAt: created + 700,
    doneAt: created + 2_400,
    options,
    result: { total_rows: 20, inserted: options.dry_run ? 20 : 18, updated: options.dry_run ? 0 : 2, skipped: 0, errors: [], dry_run: options.dry_run },
  };
  importJobs.set(job.id, job);
  return { job_id: job.id };
}

export function mockGetImportJob(jobId: string): unknown {
  const job = importJobs.get(jobId);
  if (!job) throw new Error('Задача импорта не найдена.');
  return visibleImportJob(job);
}

export function mockListImportJobs(): unknown[] {
  return [...importJobs.values()]
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .map(visibleImportJob);
}
