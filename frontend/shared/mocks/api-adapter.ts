import type { AuditEvent, AuditListQuery, AuditListResult } from '@/shared/lib/audit-repository';
import type { ImportExecuteResponse, ImportJob, ImportRunOptions } from '@/shared/lib/import-repository';
import type { CatalogInput, CatalogItem, CatalogListQuery, CatalogListResult, CatalogReferenceData, CatalogType, ResponsibleCatalogItem } from '@/shared/lib/catalogs-repository';
import { ApiRequestError } from '@/shared/lib/api-errors';
import type {
  AdminUser,
  AdminUserListQuery,
  AdminUserListResult,
  AdminUserUpdateInput,
  InviteAdminUserInput,
  ResponsibleAssignmentInput,
  ResponsibleCandidate,
} from '@/shared/lib/users-repository';
import { setMockResponsibleAssignment } from '@/shared/lib/responsible-assignments';
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
import type {
  CreateWorkflowFromExternalInput,
  CreateWorkflowFromExternalResult,
  ExternalApplication,
  ExternalDashboardMetrics,
  ExternalDataSource,
  UniversityExternalData,
} from '@/shared/lib/external-integrations-repository';

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
    user: { id: 'mock-manager', name: 'Мария Менеджер', email: 'manager@example.test' },
    role: 'manager',
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

type StoredImportFile = { filename: string };
type StoredImportJob = ImportJob & { processingAt: number; doneAt: number; options: ImportRunOptions };

const importFiles = new Map<string, StoredImportFile>();
const importJobs = new Map<string, StoredImportJob>();

/** Демо-структура тестового Импорт_CRM.xlsx: листы и объёмы. */
const mockImportSheets = [
  { id: 'ВУЗы', label: 'ВУЗы', row_count: 4 },
  { id: 'ИТ-продукты', label: 'ИТ-продукты', row_count: 6 },
  { id: 'Ответственные ВУЗа', label: 'Ответственные ВУЗа', row_count: 4 },
  { id: 'Договоры и лицензии', label: 'Договоры и лицензии', row_count: 5 },
  { id: 'Направления', label: 'Направления', row_count: 5 },
  { id: 'Программы', label: 'Программы', row_count: 8 },
  { id: 'Продукт_Направление', label: 'Продукт_Направление', row_count: 9 },
];

const mockSheetPreviews: Record<string, { headers: string[]; rows: Array<Record<string, string | number | boolean | null>>; row_count: number }> = {
  'ВУЗы': {
    headers: ['Название ВУЗа', 'Город'],
    rows: [
      { 'Название ВУЗа': 'Донецкий национальный технический университет', Город: 'Донецк' },
      { 'Название ВУЗа': 'Московский государственный университет имени М.В. Ломоносова', Город: 'Москва' },
      { 'Название ВУЗа': 'Санкт-Петербургский государственный университет', Город: 'Санкт-Петербург' },
    ],
    row_count: 4,
  },
  'ИТ-продукты': {
    headers: ['Вендор', 'ИТ-продукт'],
    rows: [
      { Вендор: 'Microsoft', 'ИТ-продукт': 'Microsoft Office' },
      { Вендор: '1С', 'ИТ-продукт': '1С:Предприятие' },
      { Вендор: 'Microsoft', 'ИТ-продукт': 'Windows' },
    ],
    row_count: 6,
  },
  'Ответственные ВУЗа': {
    headers: ['ВУЗ', 'ФИО', 'Должность', 'Email', 'Телефон'],
    rows: [
      { ВУЗ: 'Донецкий национальный технический университет', ФИО: 'Иванов Иван Иванович', Должность: 'Проректор по ИТ', Email: 'ivanov@donntu.ru', Телефон: '+7 (900) 111-22-33' },
      { ВУЗ: 'Донецкий национальный технический университет', ФИО: 'Петров Петр Петрович', Должность: 'Начальник отдела ИТ', Email: 'petrov@donntu.ru', Телефон: '+7 (900) 444-55-66' },
    ],
    row_count: 4,
  },
  'Договоры и лицензии': {
    headers: ['ВУЗ', 'Вендор', 'ИТ-продукт', 'Номер договора', 'Дата договора', 'Подписание лицензии', 'Окончание действия лицензии', 'Статус'],
    rows: [
      { ВУЗ: 'Донецкий национальный технический университет', Вендор: 'Microsoft', 'ИТ-продукт': 'Microsoft Office', 'Номер договора': '15/2026', 'Дата договора': '2026-01-15', 'Подписание лицензии': '2026-01-20', 'Окончание действия лицензии': '2027-01-31', Статус: 'Действует' },
      { ВУЗ: 'Донецкий национальный технический университет', Вендор: 'Microsoft', 'ИТ-продукт': 'Windows', 'Номер договора': '15/2026', 'Дата договора': '2026-01-15', 'Подписание лицензии': '2026-01-20', 'Окончание действия лицензии': '2027-01-31', Статус: 'Действует' },
    ],
    row_count: 5,
  },
  'Направления': {
    headers: ['Код направления', 'Название направления'],
    rows: [
      { 'Код направления': '09.03.01', 'Название направления': 'Информатика и вычислительная техника' },
      { 'Код направления': '09.03.02', 'Название направления': 'Информационные системы и технологии' },
      { 'Код направления': '10.03.01', 'Название направления': 'Информационная безопасность' },
    ],
    row_count: 5,
  },
  'Программы': {
    headers: ['Название программы', 'Направление', 'Описание'],
    rows: [
      { 'Название программы': 'Искусственный интеллект', Направление: 'Информатика и вычислительная техника', Описание: 'ML, нейросети и анализ данных' },
      { 'Название программы': 'Кибербезопасность', Направление: 'Информационная безопасность', Описание: 'Защита информации и сетей' },
    ],
    row_count: 8,
  },
  'Продукт_Направление': {
    headers: ['ID продукта', 'ID направления'],
    rows: [
      { 'ID продукта': 'Microsoft Office', 'ID направления': '09.03.02' },
      { 'ID продукта': 'Windows', 'ID направления': '09.03.01' },
      { 'ID продукта': 'Teams', 'ID направления': '11.03.02' },
    ],
    row_count: 9,
  },
};

export function mockUploadImportFile(file: File): unknown {
  const fileId = id('import-file');
  importFiles.set(fileId, { filename: file.name });
  return {
    file_id: fileId,
    filename: file.name,
    sheets: mockImportSheets.map((sheet) => ({ ...sheet })),
  };
}

export function mockPreviewImportSheet(fileId: string, sheet: string): unknown {
  if (!importFiles.has(fileId)) throw new Error('Файл импорта не найден. Загрузите его заново.');
  const found = mockSheetPreviews[sheet];
  if (!found) throw new Error(`Лист «${sheet}» не найден в файле.`);
  return {
    file_id: fileId,
    sheet,
    headers: [...found.headers],
    preview: found.rows.map((row) => ({ ...row })),
    row_count: found.row_count,
  };
}

function visibleImportJob(stored: StoredImportJob): Record<string, unknown> {
  const timestamp = Date.now();
  const status = timestamp >= stored.doneAt ? 'done' : timestamp >= stored.processingAt ? 'processing' : 'queued';
  return {
    id: stored.id,
    type: stored.type,
    status,
    progress: status === 'done' ? 100 : status === 'processing' ? 10 : 0,
    dry_run: stored.dryRun,
    created_at: stored.createdAt,
    filename: stored.filename,
    sheet: stored.sheet,
    created_by: stored.createdBy,
    result: status === 'done' ? stored.result : undefined,
  };
}

export function mockExecuteSheetImport(fileId: string, sheet: string, options: ImportRunOptions): ImportExecuteResponse {
  const file = importFiles.get(fileId);
  if (!file) throw new Error('Файл импорта не найден. Загрузите его заново.');
  const total = mockSheetPreviews[sheet]?.row_count ?? 0;
  const created = Date.now();
  const job: StoredImportJob = {
    id: id('import-job'),
    type: 'xlsx_import',
    status: 'queued',
    progress: 0,
    dryRun: options.dry_run,
    createdAt: now(),
    filename: file.filename,
    sheet,
    createdBy: 'Мария Менеджер',
    processingAt: created + 700,
    doneAt: created + 2_400,
    options,
    result: { total_rows: total, inserted: options.dry_run ? total : Math.max(0, total - 1), updated: options.dry_run ? 0 : Math.min(1, total), skipped: 0, errors: [], dry_run: options.dry_run },
  };
  importJobs.set(job.id, job);
  return { job_id: job.id };
}

export function mockExecuteSheetsImport(fileId: string, sheets: string[], options: ImportRunOptions): ImportExecuteResponse {
  const file = importFiles.get(fileId);
  if (!file) throw new Error('Файл импорта не найден. Загрузите его заново.');
  const breakdown = sheets.map((sheet) => {
    const total = mockSheetPreviews[sheet]?.row_count ?? 0;
    return {
      sheet,
      summary: {
        total_rows: total,
        inserted: options.dry_run ? total : Math.max(0, total - 1),
        updated: options.dry_run ? 0 : Math.min(1, total),
        skipped: 0,
        errors: [],
        dry_run: options.dry_run,
      },
    };
  });
  const created = Date.now();
  const job: StoredImportJob = {
    id: id('import-job'),
    type: 'xlsx_import',
    status: 'queued',
    progress: 0,
    dryRun: options.dry_run,
    createdAt: now(),
    filename: file.filename,
    sheet: `Все листы (${sheets.length})`,
    createdBy: 'Мария Менеджер',
    processingAt: created + 700,
    doneAt: created + 2_400,
    options,
    result: {
      total_rows: breakdown.reduce((total, item) => total + item.summary.total_rows, 0),
      inserted: breakdown.reduce((total, item) => total + item.summary.inserted, 0),
      updated: breakdown.reduce((total, item) => total + item.summary.updated, 0),
      skipped: 0,
      errors: [],
      dry_run: options.dry_run,
      sheets: breakdown,
    },
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

// --------------------------------------------------------------- users / RBAC

const demoAdminUsers = new Map<string, AdminUser>([
  ['1', {
    id: '1', username: 'admin', name: 'Анна Иванова', email: 'anna.ivanova@example.ru', role: 'admin', status: 'active', scope: { kind: 'all' }, lastLoginAt: '2026-09-24T09:42:00+03:00',
  }],
  ['user-manager-boris', {
    id: 'user-manager-boris', username: 'boris.petrov', name: 'Борис Петров', email: 'boris.petrov@example.ru', role: 'manager', status: 'active', scope: { kind: 'universities', universityIds: ['university-001', 'university-002', 'university-003', 'university-004'] }, lastLoginAt: '2026-09-23T18:20:00+03:00',
  }],
  ['user-elena', {
    id: 'user-elena', username: 'elena.smirnova', name: 'Елена Смирнова', email: 'elena.smirnova@example.ru', role: 'user', status: 'active', scope: { kind: 'universities', universityIds: ['university-003', 'university-007'] }, lastLoginAt: '2026-09-21T11:05:00+03:00',
  }],
]);

function copyAdminUser(user: AdminUser): AdminUser {
  return { ...user, scope: user.scope.kind === 'all' ? { kind: 'all' } : { kind: 'universities', universityIds: [...user.scope.universityIds] } };
}

function matchesUser(user: AdminUser, query: AdminUserListQuery): boolean {
  if (query.role !== 'all' && user.role !== query.role) return false;
  const search = query.search.trim().toLocaleLowerCase('ru-RU');
  return !search || `${user.name} ${user.username} ${user.email}`.toLocaleLowerCase('ru-RU').includes(search);
}

export function mockListAdminUsers(query: AdminUserListQuery): AdminUserListResult {
  const filtered = [...demoAdminUsers.values()].filter((user) => matchesUser(user, query)).sort((left, right) => left.name.localeCompare(right.name, 'ru'));
  const start = (query.page - 1) * query.pageSize;
  return { items: filtered.slice(start, start + query.pageSize).map(copyAdminUser), page: query.page, pageSize: query.pageSize, total: filtered.length };
}

function getAdminUser(id: string): AdminUser {
  const user = demoAdminUsers.get(id);
  if (!user) throw new Error('Пользователь не найден.');
  return user;
}

export function mockUpdateAdminUser(id: string, input: AdminUserUpdateInput): AdminUser {
  const user = getAdminUser(id);
  const next: AdminUser = { ...user, role: input.role, scope: input.role === 'admin' ? { kind: 'all' } : copyAdminUser({ ...user, scope: input.scope }).scope };
  demoAdminUsers.set(id, next);
  return copyAdminUser(next);
}

export function mockBlockAdminUser(id: string, blocked: boolean): AdminUser {
  const user = getAdminUser(id);
  const next: AdminUser = { ...user, status: blocked ? 'blocked' : 'active' };
  demoAdminUsers.set(id, next);
  return copyAdminUser(next);
}

export function mockInviteAdminUser(input: InviteAdminUserInput): AdminUser {
  const invited: AdminUser = {
    id: id('user'),
    username: input.username,
    name: input.name,
    email: input.email,
    role: input.role,
    status: 'active',
    scope: input.role === 'admin' ? { kind: 'all' } : input.scope,
    lastLoginAt: null,
  };
  demoAdminUsers.set(invited.id, invited);
  return copyAdminUser(invited);
}

export function mockResetAdminUserPassword(id: string): { status: 'requested'; actionUrl?: string } {
  getAdminUser(id);
  return { status: 'requested', actionUrl: '/login?reset=demo' };
}

export function mockListResponsibleCandidates(): ResponsibleCandidate[] {
  return responsibleCatalogItems().filter((item) => item.isActive).map((item) => ({ id: item.id, name: item.name, email: item.email, role: item.role }));
}

export function mockAssignUniversityResponsible(input: ResponsibleAssignmentInput): void {
  const candidate = mockListResponsibleCandidates().find((item) => item.id === input.responsibleId);
  if (!candidate) throw new Error('Ответственный не найден.');
  setMockResponsibleAssignment(input.universityId, { responsibleId: candidate.id, reason: input.reason, assignedAt: new Date().toISOString() });
}

// -------------------------------------------------------------- external integrations

const mockExternalSyncAt = '2026-09-24T08:45:00.000Z';

function externalIndex(universityId: string): number {
  const digits = universityId.match(/\d+/)?.[0];
  return Math.max(1, Number(digits ?? 1));
}

function mockWebsiteApplications(universityId: string): ExternalApplication[] {
  const index = externalIndex(universityId);
  const definitions = [
    ['Аналитика данных', 12 + index, 82],
    ['Информационная безопасность', 8 + index, 67],
    ['ИТ-менеджмент', 5 + index, 49],
  ] as const;
  return definitions.map(([programName, applicationsCount, demandScore], position) => ({
    id: `website-${universityId}-${position + 1}`,
    universityId,
    programId: `program-${universityId}-${position + 1}`,
    programName,
    applicationsCount,
    demandScore,
    source: 'website' as const,
    syncedAt: mockExternalSyncAt,
    workflowInstanceId: readSession<string | null>(`external-workflow:${universityId}:website-${universityId}-${position + 1}`, null),
  }));
}

export function mockGetUniversityExternalData(universityId: string, source: ExternalDataSource): UniversityExternalData {
  return { universityId, source, mode: 'mock', syncedAt: mockExternalSyncAt, students: [], applications: mockWebsiteApplications(universityId) };
}

export function mockCreateWorkflowFromExternal(input: CreateWorkflowFromExternalInput): CreateWorkflowFromExternalResult {
  const storageKey = `external-workflow:${input.universityId}:${input.externalId}`;
  const programId = mockWebsiteApplications(input.universityId).find((row) => row.id === input.externalId)?.programId ?? null;
  const existing = readSession<string | null>(storageKey, null);
  if (existing) {
    return { instanceId: existing, universityId: input.universityId, programId, externalId: input.externalId, existing: true };
  }

  const instanceId = id('mock-external-workflow');
  writeSession(storageKey, instanceId);
  registerMockWorkflow({
    instanceId,
    universityId: input.universityId,
    universityName: 'Университет из внешнего источника',
    currentStageId: `${instanceId}-workflow-stage-1`,
    stages: ['Инициация проекта', 'Проверка заявки', 'Согласование программы', 'Запуск обучения']
      .map((name, index) => ({ id: `${instanceId}-workflow-stage-${index + 1}`, name, orderIndex: index + 1, isRequired: true })),
  });
  return { instanceId, universityId: input.universityId, programId, externalId: input.externalId, existing: false };
}

export function mockGetExternalDashboardMetrics(): ExternalDashboardMetrics {
  return {
    mode: 'mock',
    websiteApplications7d: 38,
    lmsStudents: 126,
    websiteSyncedAt: mockExternalSyncAt,
    lmsSyncedAt: mockExternalSyncAt,
  };
}

// -------------------------------------------------------------- catalog CRUD

const catalogSeedTimestamp = '2026-09-20T09:00:00.000Z';
const mockVendors = [
  { id: 'vendor-rostelecom', name: 'Ростелеком' },
  { id: 'vendor-red-soft', name: 'РЕД СОФТ' },
  { id: 'vendor-kontur', name: 'Контур' },
];

const catalogSeeds: CatalogItem[] = [
  { id: 'university-001', type: 'universities', name: 'Московский технический университет связи и информатики', city: 'Москва', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'university-002', type: 'universities', name: 'Санкт-Петербургский политехнический университет', city: 'Санкт-Петербург', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'university-003', type: 'universities', name: 'Уральский федеральный университет', city: 'Екатеринбург', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'university-004', type: 'universities', name: 'Казанский федеральный университет', city: 'Казань', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'university-005', type: 'universities', name: 'Новосибирский государственный университет', city: 'Новосибирск', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'university-archived', type: 'universities', name: 'Архивный демонстрационный ВУЗ', city: 'Москва', isActive: false, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'product-professional-retraining', type: 'products', name: 'Профессиональная переподготовка', vendorId: 'vendor-rostelecom', vendorName: 'Ростелеком', version: '2026', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'product-short-courses', type: 'products', name: 'Короткие курсы', vendorId: 'vendor-kontur', vendorName: 'Контур', version: '3.2', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'product-corporate-track', type: 'products', name: 'Корпоративный трек', vendorId: 'vendor-rostelecom', vendorName: 'Ростелеком', version: '2026.1', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'product-archived', type: 'products', name: 'Архивный продукт', vendorId: 'vendor-red-soft', vendorName: 'РЕД СОФТ', version: '1.0', isActive: false, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'direction-data', type: 'directions', name: 'Аналитика данных', code: 'data', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'direction-cybersecurity', type: 'directions', name: 'Информационная безопасность', code: 'cybersecurity', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'direction-management', type: 'directions', name: 'ИТ-менеджмент', code: 'it-management', isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'direction-archived', type: 'directions', name: 'Архивное направление', code: 'archive', isActive: false, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'responsible-anna', type: 'responsibles', name: 'Анна Иванова', email: 'anna.ivanova@example.ru', phone: '+7 495 000-00-01', role: 'Куратор проекта', universityIds: ['university-001', 'university-005'], isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'responsible-boris', type: 'responsibles', name: 'Борис Петров', email: 'boris.petrov@example.ru', phone: '+7 495 000-00-02', role: 'Менеджер', universityIds: ['university-002', 'university-004'], isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'responsible-elena', type: 'responsibles', name: 'Елена Смирнова', email: 'elena.smirnova@example.ru', phone: '+7 495 000-00-03', role: 'Координатор программы', universityIds: ['university-003'], isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'responsible-dmitry', type: 'responsibles', name: 'Дмитрий Волков', email: 'dmitry.volkov@example.ru', phone: '', role: 'Менеджер', universityIds: ['university-004'], isActive: true, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
  { id: 'responsible-archived', type: 'responsibles', name: 'Архивный ответственный', email: 'archive@example.ru', phone: '', role: 'Координатор', universityIds: [], isActive: false, createdAt: catalogSeedTimestamp, updatedAt: catalogSeedTimestamp },
];

const mockCatalogs = new Map<CatalogType, Map<string, CatalogItem>>();
for (const item of catalogSeeds) {
  const group = mockCatalogs.get(item.type) ?? new Map<string, CatalogItem>();
  group.set(item.id, item);
  mockCatalogs.set(item.type, group);
}

function cloneCatalogItem(item: CatalogItem): CatalogItem {
  return item.type === 'responsibles' ? { ...item, universityIds: [...item.universityIds] } : { ...item };
}

function catalogGroup(type: CatalogType): Map<string, CatalogItem> {
  return mockCatalogs.get(type) ?? new Map<string, CatalogItem>();
}

function responsibleCatalogItems(): ResponsibleCatalogItem[] {
  return [...catalogGroup('responsibles').values()].filter((item): item is ResponsibleCatalogItem => item.type === 'responsibles');
}

function catalogSearchText(item: CatalogItem): string {
  if (item.type === 'universities') return `${item.name} ${item.city}`;
  if (item.type === 'products') return `${item.name} ${item.vendorName} ${item.version}`;
  if (item.type === 'directions') return `${item.name} ${item.code}`;
  return `${item.name} ${item.email} ${item.role}`;
}

export function mockListCatalogItems(query: CatalogListQuery): CatalogListResult {
  const search = query.search.trim().toLocaleLowerCase('ru-RU');
  const filtered = [...catalogGroup(query.type).values()]
    .filter((item) => (query.showInactive || item.isActive) && (!search || catalogSearchText(item).toLocaleLowerCase('ru-RU').includes(search)))
    .sort((left, right) => left.name.localeCompare(right.name, 'ru'));
  const start = (query.page - 1) * query.pageSize;
  return { items: filtered.slice(start, start + query.pageSize).map(cloneCatalogItem), page: query.page, pageSize: query.pageSize, total: filtered.length };
}

export function mockGetCatalogItem(type: CatalogType, itemId: string): CatalogItem {
  const item = catalogGroup(type).get(itemId);
  if (!item) throw new ApiRequestError(404, { code: 'ENTITY_NOT_FOUND' }, 'Запись каталога не найдена.');
  return cloneCatalogItem(item);
}

export function mockGetCatalogReferenceData(): CatalogReferenceData {
  return {
    vendors: mockVendors.map((item) => ({ ...item })),
    universities: [...catalogGroup('universities').values()].filter((item) => item.type === 'universities' && item.isActive).map((item) => ({ id: item.id, name: item.name })),
    products: [...catalogGroup('products').values()].flatMap((item) => item.type === 'products' && item.isActive ? [{ id: item.id, name: item.name, description: item.vendorName }] : []),
    directions: [...catalogGroup('directions').values()].flatMap((item) => item.type === 'directions' && item.isActive ? [{ id: item.id, name: item.name, description: item.code }] : []),
    programs: [
      { id: 'program-data-analytics', name: 'Аналитика данных' },
      { id: 'program-digital-economy', name: 'Цифровая экономика' },
      { id: 'program-it-management', name: 'ИТ-менеджмент' },
      { id: 'program-cybersecurity', name: 'Кибербезопасность' },
    ],
    responsibles: [...catalogGroup('responsibles').values()].flatMap((item) => item.type === 'responsibles' && item.isActive ? [{ id: item.id, name: item.name, description: item.role || item.email }] : []),
  };
}

function duplicateCatalogItem(input: CatalogInput, exceptId?: string): boolean {
  const values = [...catalogGroup(input.type).values()].filter((item) => item.id !== exceptId);
  if (input.type === 'universities') return values.some((item) => item.name.toLocaleLowerCase('ru-RU') === input.name.toLocaleLowerCase('ru-RU'));
  if (input.type === 'directions') return values.some((item) => item.type === 'directions' && item.code.toLocaleLowerCase('ru-RU') === input.code.toLocaleLowerCase('ru-RU'));
  if (input.type === 'products') return values.some((item) => item.type === 'products' && item.vendorId === input.vendorId && item.name.toLocaleLowerCase('ru-RU') === input.name.toLocaleLowerCase('ru-RU') && item.version === input.version);
  return values.some((item) => item.type === 'responsibles' && item.email.toLocaleLowerCase('ru-RU') === input.email.toLocaleLowerCase('ru-RU'));
}

function catalogItemFromInput(input: CatalogInput, current?: CatalogItem): CatalogItem {
  const timestamp = now();
  const base = { id: current?.id ?? id(input.type.slice(0, -1)), name: input.name, isActive: current?.isActive ?? true, createdAt: current?.createdAt ?? timestamp, updatedAt: timestamp };
  if (input.type === 'universities') return { ...base, type: input.type, city: input.city };
  if (input.type === 'products') return { ...base, type: input.type, vendorId: input.vendorId, vendorName: mockVendors.find((item) => item.id === input.vendorId)?.name ?? '—', version: input.version };
  if (input.type === 'directions') return { ...base, type: input.type, code: input.code };
  return { ...base, type: input.type, email: input.email, phone: input.phone, role: input.role, universityIds: [...input.universityIds] };
}

export function mockCreateCatalogItem(input: CatalogInput): CatalogItem {
  if (duplicateCatalogItem(input)) throw new ApiRequestError(409, { code: 'DUPLICATE_ENTITY' }, 'Такая запись уже существует.');
  const item = catalogItemFromInput(input);
  catalogGroup(input.type).set(item.id, item);
  return cloneCatalogItem(item);
}

export function mockUpdateCatalogItem(itemId: string, input: CatalogInput): CatalogItem {
  const current = mockGetCatalogItem(input.type, itemId);
  if (duplicateCatalogItem(input, itemId)) throw new ApiRequestError(409, { code: 'DUPLICATE_ENTITY' }, 'Такая запись уже существует.');
  const item = catalogItemFromInput(input, current);
  catalogGroup(input.type).set(item.id, item);
  return cloneCatalogItem(item);
}

export function mockSetCatalogItemActive(type: CatalogType, itemId: string, active: boolean): CatalogItem {
  const current = mockGetCatalogItem(type, itemId);
  const item = { ...current, isActive: active, updatedAt: now() } as CatalogItem;
  catalogGroup(type).set(item.id, item);
  return cloneCatalogItem(item);
}
