import { programStatusLabels, type ProgramStatus } from './dashboard-repository';
import { apiDownload, apiFetch, apiUploadFormData } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource, isMockDataSource, isMockDataSourceFor } from './data-source';
import { queryKeys } from './query-keys';
import type { QueryClient } from '@tanstack/react-query';
import { getMockResponsibleAssignment } from './responsible-assignments';
import {
  getMockWorkflowCurrentStageId,
  mockCreateWorkflowComment,
  mockEditWorkflowComment,
  mockGetWorkflowInstance,
  mockListWorkflowComments,
  mockRollbackWorkflow,
  mockTransitionWorkflow,
  registerMockWorkflow,
} from '@/shared/mocks/api-adapter';
import {
  realGetUniversities,
  realGetUniversityMap,
  realGetUniversityDocuments,
  realGetUniversityHistory,
  realGetUniversityLicenses,
  realGetUniversityMeetings,
  realGetUniversityPassport,
  realGetUniversityProducts,
  realGetUniversityPrograms,
  realGetUniversityResponsibles,
} from './real-api-adapter';

export type { ProgramStatus };

export interface UniversityResponsible {
  id: string;
  name: string;
  email?: string;
  role?: string;
}

export interface UniversityStage {
  id: string;
  name: string;
  tone: 'neutral' | 'brand' | 'warning' | 'success';
}

export type ProgramStatusCounts = Partial<Record<ProgramStatus, number>>;

export interface UniversityListItem {
  id: string;
  name: string;
  city: string;
  responsible: UniversityResponsible | null;
  programsCount: number;
  programStatusCounts: ProgramStatusCounts;
  currentStage: UniversityStage;
  lastInteractionAt: string;
  attention: boolean;
  availability?: {
    responsible: boolean;
    programs: boolean;
    stage: boolean;
    lastInteraction: boolean;
  };
  /** Mock relationship ids mirror the fields expected from the future analytics API. */
  programIds?: string[];
  productIds?: string[];
}

export interface UniversityMapItem {
  id: string;
  name: string;
  city: string;
  regionCode: string | null;
  programsCount: number;
  launchedPrograms: number;
  activePrograms: number;
  activeWorkflow: boolean;
  responsibleName: string | null;
}

export type UniversitySortColumn = 'name' | 'responsible' | 'programs' | 'stage' | 'last_interaction';
export type SortOrder = 'asc' | 'desc';

export interface UniversityFilters {
  externalSource: 'lms' | 'website' | '';
  search: string;
  cities: string[];
  universityIds: string[];
  programIds: string[];
  productIds: string[];
  responsibleIds: string[];
  workflowStageIds: string[];
  dateFrom: string;
  dateTo: string;
}

export interface UniversityListQuery {
  filters: UniversityFilters;
  sort: UniversitySortColumn | null;
  order: SortOrder;
  page: number;
  pageSize: number;
}

export interface PaginatedResult<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface UniversityFilterOptions {
  cities: string[];
  responsibles: UniversityResponsible[];
  stages: UniversityStage[];
  universities: Array<{ id: string; name: string }>;
  programs: Array<{ id: string; name: string }>;
  products: Array<{ id: string; name: string }>;
}

export { programStatusLabels };

export const UNIVERSITY_LIST_CAPABILITIES = isMockDataSourceFor('universities')
  ? {
      filters: { university: true, program: true, product: true, responsible: true, stage: true, date: true },
      sorts: { name: true, responsible: true, programs: true, stage: true, last_interaction: true },
      dateMeaning: 'last-interaction' as const,
    }
  : {
      filters: { university: true, program: true, product: true, responsible: true, stage: true, date: true },
      sorts: { name: true, responsible: false, programs: false, stage: false, last_interaction: false },
      dateMeaning: 'interaction-period' as const,
    };

export const UNIVERSITY_PASSPORT_CAPABILITIES = isMockDataSourceFor('passport')
  ? { programStatusFilter: true, documentFilters: true, externalData: true, mutations: true }
  : { programStatusFilter: true, documentFilters: true, externalData: true, mutations: false };
// External LMS/website methods share the same Mock ↔ Real repository boundary.
export {
  createWorkflowFromExternal,
  getExternalDashboardMetrics,
  getUniversityExternalData,
  isExternalSourceUnavailable,
  universityExternalDataQueryKey,
} from './external-integrations-repository';
export type {
  CreateWorkflowFromExternalInput,
  CreateWorkflowFromExternalResult,
  ExternalApplication,
  ExternalDashboardMetrics,
  ExternalDataSource,
  UniversityExternalData,
} from './external-integrations-repository';

const programCounts = (planned: number, active: number, launched = 0, archived = 0): ProgramStatusCounts => ({
  planned,
  active,
  launched,
  archived,
});

const responsible = {
  anna: { id: 'responsible-anna', name: 'Анна Иванова', email: 'anna.ivanova@example.ru', role: 'Куратор проекта' },
  boris: { id: 'responsible-boris', name: 'Борис Петров', email: 'boris.petrov@example.ru', role: 'Менеджер' },
  elena: { id: 'responsible-elena', name: 'Елена Смирнова', email: 'elena.smirnova@example.ru', role: 'Координатор программы' },
  dmitry: { id: 'responsible-dmitry', name: 'Дмитрий Волков', email: 'dmitry.volkov@example.ru', role: 'Менеджер' },
} satisfies Record<string, UniversityResponsible>;

function assignedMockResponsible(universityId: string): UniversityResponsible | null | undefined {
  const assignment = getMockResponsibleAssignment(universityId);
  if (!assignment) return undefined;
  return Object.values(responsible).find((item) => item.id === assignment.responsibleId) ?? null;
}

const stage = {
  preparation: { id: 'preparation', name: 'Подготовка', tone: 'neutral' },
  launch: { id: 'launch', name: 'Запуск программы', tone: 'brand' },
  support: { id: 'support', name: 'Сопровождение', tone: 'warning' },
  completed: { id: 'completed', name: 'Завершён', tone: 'success' },
} satisfies Record<string, UniversityStage>;

const universitiesMock: UniversityListItem[] = [
  { id: 'university-001', name: 'Московский технический университет связи и информатики', city: 'Москва', responsible: responsible.anna, programsCount: 12, programStatusCounts: programCounts(2, 5, 4, 1), currentStage: stage.support, lastInteractionAt: '2026-09-19T10:30:00+03:00', attention: true },
  { id: 'university-002', name: 'Санкт-Петербургский политехнический университет', city: 'Санкт-Петербург', responsible: responsible.boris, programsCount: 8, programStatusCounts: programCounts(1, 4, 3), currentStage: stage.launch, lastInteractionAt: '2026-09-17T14:00:00+03:00', attention: true },
  { id: 'university-003', name: 'Уральский федеральный университет', city: 'Екатеринбург', responsible: responsible.elena, programsCount: 6, programStatusCounts: programCounts(2, 2, 2), currentStage: stage.preparation, lastInteractionAt: '2026-09-13T09:15:00+03:00', attention: true },
  { id: 'university-004', name: 'Казанский федеральный университет', city: 'Казань', responsible: responsible.dmitry, programsCount: 10, programStatusCounts: programCounts(1, 5, 4), currentStage: stage.support, lastInteractionAt: '2026-09-18T16:45:00+03:00', attention: true },
  { id: 'university-005', name: 'Новосибирский государственный университет', city: 'Новосибирск', responsible: responsible.anna, programsCount: 5, programStatusCounts: programCounts(1, 2, 2), currentStage: stage.preparation, lastInteractionAt: '2026-09-20T11:10:00+03:00', attention: true },
  { id: 'university-006', name: 'Дальневосточный федеральный университет', city: 'Владивосток', responsible: responsible.boris, programsCount: 7, programStatusCounts: programCounts(2, 3, 2), currentStage: stage.launch, lastInteractionAt: '2026-09-16T13:20:00+03:00', attention: false },
  { id: 'university-007', name: 'Южный федеральный университет', city: 'Ростов-на-Дону', responsible: responsible.elena, programsCount: 4, programStatusCounts: programCounts(1, 1, 2), currentStage: stage.completed, lastInteractionAt: '2026-09-12T15:30:00+03:00', attention: false },
  { id: 'university-008', name: 'Самарский университет имени академика Королёва', city: 'Самара', responsible: null, programsCount: 3, programStatusCounts: programCounts(1, 2), currentStage: stage.preparation, lastInteractionAt: '2026-09-10T08:40:00+03:00', attention: false },
  { id: 'university-009', name: 'Национальный исследовательский ядерный университет МИФИ', city: 'Москва', responsible: responsible.dmitry, programsCount: 11, programStatusCounts: programCounts(1, 5, 5), currentStage: stage.support, lastInteractionAt: '2026-09-15T12:00:00+03:00', attention: false },
  { id: 'university-010', name: 'Томский государственный университет', city: 'Томск', responsible: responsible.anna, programsCount: 9, programStatusCounts: programCounts(2, 3, 4), currentStage: stage.launch, lastInteractionAt: '2026-09-14T17:25:00+03:00', attention: false },
  { id: 'university-011', name: 'Нижегородский государственный университет имени Лобачевского', city: 'Нижний Новгород', responsible: responsible.boris, programsCount: 2, programStatusCounts: programCounts(1, 1), currentStage: stage.preparation, lastInteractionAt: '2026-09-08T10:05:00+03:00', attention: true },
  { id: 'university-012', name: 'Воронежский государственный университет', city: 'Воронеж', responsible: responsible.elena, programsCount: 6, programStatusCounts: programCounts(1, 3, 2), currentStage: stage.completed, lastInteractionAt: '2026-09-19T09:45:00+03:00', attention: false },
  { id: 'university-013', name: 'Пермский национальный исследовательский политехнический университет', city: 'Пермь', responsible: responsible.dmitry, programsCount: 5, programStatusCounts: programCounts(2, 2, 1), currentStage: stage.support, lastInteractionAt: '2026-09-06T14:35:00+03:00', attention: false },
  { id: 'university-014', name: 'Балтийский федеральный университет имени Иммануила Канта', city: 'Калининград', responsible: null, programsCount: 3, programStatusCounts: programCounts(1, 1, 1), currentStage: stage.launch, lastInteractionAt: '2026-09-11T16:10:00+03:00', attention: false },
  { id: 'university-015', name: 'Сибирский федеральный университет', city: 'Красноярск', responsible: responsible.anna, programsCount: 8, programStatusCounts: programCounts(1, 4, 3), currentStage: stage.support, lastInteractionAt: '2026-09-18T09:00:00+03:00', attention: false },
  { id: 'university-016', name: 'Московский государственный технический университет имени Баумана', city: 'Москва', responsible: responsible.boris, programsCount: 13, programStatusCounts: programCounts(2, 6, 5), currentStage: stage.completed, lastInteractionAt: '2026-09-20T13:50:00+03:00', attention: false },
  { id: 'university-017', name: 'Омский государственный технический университет', city: 'Омск', responsible: responsible.elena, programsCount: 4, programStatusCounts: programCounts(1, 2, 1), currentStage: stage.preparation, lastInteractionAt: '2026-09-05T11:30:00+03:00', attention: true },
  { id: 'university-018', name: 'Саратовский государственный университет', city: 'Саратов', responsible: responsible.dmitry, programsCount: 7, programStatusCounts: programCounts(1, 3, 3), currentStage: stage.launch, lastInteractionAt: '2026-09-16T10:20:00+03:00', attention: false },
];

export const universitiesQueryKey = queryKeys.universities.all;
export const universitiesListQueryKey = queryKeys.universities.list;
export const universitiesMapQueryKey = queryKeys.universities.map;
export const universityStageOptionsQueryKey = ['universities', 'stage-options'] as const;

export async function createUniversity(input: { name: string; city: string | null }): Promise<{ id: string }> {
  const result = await apiFetch<{ id: string }>('/api/v1/universities', { method: 'POST', body: input });
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось создать вуз.', result.error);
  return result.data;
}

export async function getUniversityStageOptions(signal?: AbortSignal): Promise<UniversityStage[]> {
  if (isMockDataSourceFor('universities')) return universityFilterOptions.stages;
  const result = await apiFetch<string[]>('/api/v1/universities/stage-options', { signal });
  if (!result.ok) throw new Error('Не удалось загрузить список этапов.');
  return result.data.map((name) => ({ id: name, name, tone: 'brand' as const }));
}

export const universityFilterOptions: UniversityFilterOptions = {
  cities: [...new Set(universitiesMock.map((item) => item.city))].sort((a, b) => a.localeCompare(b, 'ru')),
  responsibles: Object.values(responsible).sort((a, b) => a.name.localeCompare(b.name, 'ru')),
  stages: Object.values(stage),
  universities: universitiesMock.map(({ id, name }) => ({ id, name })),
  programs: [
    { id: 'program-data-analytics', name: 'Аналитика данных' },
    { id: 'program-digital-economy', name: 'Цифровая экономика' },
    { id: 'program-it-management', name: 'ИТ-менеджмент' },
    { id: 'program-cybersecurity', name: 'Кибербезопасность' },
  ],
  products: [
    { id: 'product-professional-retraining', name: 'Профессиональная переподготовка' },
    { id: 'product-short-courses', name: 'Короткие курсы' },
    { id: 'product-corporate-track', name: 'Корпоративный трек' },
  ],
};

const programOptionIds = universityFilterOptions.programs.map((item) => item.id);
const productOptionIds = universityFilterOptions.products.map((item) => item.id);
const universitiesWithRelationships = universitiesMock.map((item, index) => ({
  ...item,
  programIds: [programOptionIds[index % programOptionIds.length], programOptionIds[(index + 1) % programOptionIds.length]],
  productIds: [productOptionIds[index % productOptionIds.length]],
}));

const observedUniversities = new Map<string, UniversityListItem>();

function compareValues(left: string | number, right: string | number): number {
  if (typeof left === 'number' && typeof right === 'number') return left - right;
  return String(left).localeCompare(String(right), 'ru', { sensitivity: 'base' });
}

async function getMockUniversities(params: UniversityListQuery): Promise<PaginatedResult<UniversityListItem>> {
  const { filters } = params;
  const search = filters.search.trim().toLocaleLowerCase('ru-RU');
  const currentUniversities = universitiesWithRelationships.map((item) => {
    const assigned = assignedMockResponsible(item.id);
    return assigned === undefined ? item : { ...item, responsible: assigned };
  });
  let filtered = currentUniversities.filter((item) => {
    if (search && !item.name.toLocaleLowerCase('ru-RU').includes(search)) return false;
    if (filters.cities.length && !filters.cities.includes(item.city)) return false;
    if (filters.universityIds.length && !filters.universityIds.includes(item.id)) return false;
    if (filters.programIds.length && !filters.programIds.some((id) => item.programIds?.includes(id))) return false;
    if (filters.productIds.length && !filters.productIds.some((id) => item.productIds?.includes(id))) return false;
    if (filters.responsibleIds.length && (!item.responsible || !filters.responsibleIds.includes(item.responsible.id))) return false;
    if (filters.workflowStageIds.length && !filters.workflowStageIds.includes(item.currentStage.id)) return false;
    const interactionDate = item.lastInteractionAt.slice(0, 10);
    if (filters.dateFrom && interactionDate < filters.dateFrom) return false;
    if (filters.dateTo && interactionDate > filters.dateTo) return false;
    return true;
  });

  if (params.sort) {
    filtered = [...filtered].sort((left, right) => {
      const leftValue = params.sort === 'responsible' ? left.responsible?.name ?? ''
        : params.sort === 'programs' ? left.programsCount
          : params.sort === 'stage' ? left.currentStage.name
            : params.sort === 'last_interaction' ? left.lastInteractionAt
              : left.name;
      const rightValue = params.sort === 'responsible' ? right.responsible?.name ?? ''
        : params.sort === 'programs' ? right.programsCount
          : params.sort === 'stage' ? right.currentStage.name
            : params.sort === 'last_interaction' ? right.lastInteractionAt
              : right.name;
      return compareValues(leftValue, rightValue) * (params.order === 'desc' ? -1 : 1);
    });
  }

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / params.pageSize));
  const page = Math.min(Math.max(1, params.page), totalPages);
  const start = (page - 1) * params.pageSize;

  return {
    items: filtered.slice(start, start + params.pageSize),
    page,
    pageSize: params.pageSize,
    total,
  };
}

export async function getUniversities(params: UniversityListQuery, signal?: AbortSignal): Promise<PaginatedResult<UniversityListItem>> {
  const result = await fromDataSource({
    domain: 'universities',
    signal,
    mock: () => getMockUniversities(params),
    real: () => realGetUniversities(params, signal),
  });
  result.items.forEach((item) => observedUniversities.set(item.id, item));
  return result;
}

const mockRegionByCity: Record<string, string> = {
  'Москва': 'RU.48', 'Санкт-Петербург': 'RU.66', 'Екатеринбург': 'RU.71',
  'Казань': 'RU.73', 'Новосибирск': 'RU.53', 'Владивосток': 'RU.59',
  'Ростов-на-Дону': 'RU.61', 'Самара': 'RU.65', 'Томск': 'RU.75',
  'Нижний Новгород': 'RU.51', 'Воронеж': 'RU.86', 'Пермь': 'RU.90',
  'Калининград': 'RU.23', 'Красноярск': 'RU.91', 'Омск': 'RU.54', 'Саратов': 'RU.67',
};

export async function getUniversityMap(filters: UniversityFilters, signal?: AbortSignal): Promise<UniversityMapItem[]> {
  return fromDataSource({
    domain: 'universities', signal,
    mock: async () => (await getMockUniversities({ filters, sort: null, order: 'asc', page: 1, pageSize: universitiesMock.length })).items.map((item) => ({
      id: item.id, name: item.name, city: item.city, regionCode: mockRegionByCity[item.city] ?? null,
      programsCount: item.programsCount, launchedPrograms: item.programStatusCounts.launched ?? 0,
      activePrograms: item.programStatusCounts.active ?? 0, activeWorkflow: item.currentStage.id !== 'completed',
      responsibleName: item.responsible?.name ?? null,
    })),
    real: () => realGetUniversityMap(filters, signal),
  });
}

export type UniversityPassportEventType = 'meeting' | 'document' | 'workflow' | 'note';

export interface UniversityPassportMetrics {
  activePrograms: number;
  licenses: { active: number; expiring: number; overdue: number };
  documents: { total: number; signed: number; overdue: number; limited?: boolean };
}

export interface UniversityPassportWorkflow {
  currentStage: UniversityStage;
  status: 'in_progress' | 'completed' | 'attention';
  deadline: string;
  overdue: boolean;
  responsible: UniversityResponsible | null;
  completedSteps: number;
  totalSteps: number;
  nextStage: UniversityStage | null;
}

export interface UniversityPassportEvent {
  id: string;
  type: UniversityPassportEventType;
  occurredAt: string;
  description: string;
}

export interface UniversityPassport {
  id: string;
  name: string;
  city: string;
  timeZone?: string | null;
  metrics: UniversityPassportMetrics;
  workflow: UniversityPassportWorkflow;
  timeline: UniversityPassportEvent[];
}

const workflowOrder = [stage.preparation, stage.launch, stage.support, stage.completed];

function getPassportNextStage(currentStageId: string): UniversityStage | null {
  const currentIndex = workflowOrder.findIndex((item) => item.id === currentStageId);
  return currentIndex >= 0 && currentIndex < workflowOrder.length - 1 ? workflowOrder[currentIndex + 1] : null;
}

/**
 * Typed frontend fixture for the future GET /universities/{id}/passport adapter.
 * Keeping this mapper next to the existing university repository lets the UI
 * switch to a real source without changing passport components.
 */
async function getMockUniversityPassport(id: string): Promise<UniversityPassport> {
  const university = getUniversityOrThrow(id);

  const assignedResponsible = assignedMockResponsible(id);
  const currentResponsible = assignedResponsible === undefined ? university.responsible : assignedResponsible;

  const launchedPrograms = university.programStatusCounts.launched ?? 0;
  const activePrograms = launchedPrograms + (university.programStatusCounts.active ?? 0);
  const numericId = getUniversityNumericId(id);
  const workflowStatus: UniversityPassportWorkflow['status'] = university.currentStage.id === stage.completed.id
    ? 'completed'
    : university.attention ? 'attention' : 'in_progress';

  return {
    id: university.id,
    name: university.name,
    city: university.city,
    metrics: {
      activePrograms,
      licenses: { active: 4 + (numericId % 3), expiring: university.attention ? 2 : 1, overdue: university.attention ? 1 : 0 },
      documents: { total: 24 + numericId, signed: 19 + (numericId % 4), overdue: university.attention ? 2 : 0 },
    },
    workflow: {
      currentStage: university.currentStage,
      status: workflowStatus,
      deadline: university.attention ? '2026-09-18' : '2026-10-08',
      overdue: university.attention && university.currentStage.id !== stage.completed.id,
      responsible: currentResponsible,
      completedSteps: university.currentStage.id === stage.completed.id ? 6 : Math.max(1, workflowOrder.findIndex((item) => item.id === university.currentStage.id) + 2),
      totalSteps: 6,
      nextStage: getPassportNextStage(university.currentStage.id),
    },
    timeline: [
      { id: `${id}-event-2`, type: 'document', occurredAt: '2026-09-18T16:10:00+03:00', description: 'Получили подписанный пакет документов.' },
      { id: `${id}-event-3`, type: 'workflow', occurredAt: '2026-09-16T13:45:00+03:00', description: `Этап изменён: ${university.currentStage.name}.` },
      { id: `${id}-event-4`, type: 'note', occurredAt: '2026-09-14T09:20:00+03:00', description: 'Добавили заметку по подготовке преподавателей.' },
    ],
  };
}

export async function getUniversityPassport(id: string, queryClient?: QueryClient): Promise<UniversityPassport> {
  return fromDataSource({ domain: 'passport', mock: () => getMockUniversityPassport(id), real: () => realGetUniversityPassport(id, queryClient) });
}

export type UniversityWorkflowStageStatus = 'completed' | 'current' | 'pending' | 'skipped' | 'overdue';

export interface UniversityWorkflowComment {
  id: string;
  author: string;
  authorId?: string;
  authorRole?: string;
  isSystem?: boolean;
  occurredAt: string;
  updatedAt?: string;
  text: string;
  canEdit?: boolean;
  canDelete?: boolean;
  isOptimistic?: boolean;
  attachments?: UniversityWorkflowAttachment[];
  questionStatus?: 'none' | 'open' | 'resolved';
}

export interface UniversityWorkflowAttachment {
  id: string;
  fileName: string;
  fileType: string;
  fileSize: string;
  mimeType?: string;
  fileSizeBytes?: number;
  uploadedBy?: UniversityResponsible | null;
  uploadedAt?: string;
  description?: string;
  downloadUrl?: string;
  previewUrl?: string;
  canDelete?: boolean;
}

export interface UniversityWorkflowTask {
  id: string;
  label: string;
  completed: boolean;
}

export interface UniversityWorkflowTransition {
  id: string;
  occurredAt: string;
  actor: string;
  fromStatus: UniversityWorkflowStageStatus;
  toStatus: UniversityWorkflowStageStatus;
  comment: string;
  description?: string;
}

export interface UniversityWorkflowStage {
  id: string;
  templateStageId?: string | null;
  orderIndex: number;
  name: string;
  status: UniversityWorkflowStageStatus;
  deadline: string;
  startedAt: string | null;
  completedAt: string | null;
  completion: 'on_time' | 'late' | null;
  isOptional?: boolean;
  responsible: UniversityResponsible | null;
  responsibleOverrideId?: string | null;
  comments: UniversityWorkflowComment[];
  attachments: UniversityWorkflowAttachment[];
  tasks: UniversityWorkflowTask[];
  taskTotal?: number;
  taskCompleted?: number;
  commentTotal?: number | null;
  attachmentTotal?: number | null;
  transitions: UniversityWorkflowTransition[];
}

export interface UniversityWorkflow {
  templateId?: string;
  status?: string;
  universityId: string;
  universityName: string;
  universityCity: string;
  programId?: string | null;
  workflowName: string;
  responsibleId: string | null;
  responsibleName: string | null;
  responsibleEmail: string | null;
  responsiblePhone: string | null;
  currentStage: UniversityWorkflowStage | null;
  completedSteps: number;
  totalSteps: number;
  stages: UniversityWorkflowStage[];
}

export const workflowQueryKey = queryKeys.universities.workflow;
export const universityWorkflowQueryKey = workflowQueryKey;
export const workflowCommentsQueryKey = queryKeys.universities.workflowComments;
export const workflowByProgramQueryKey = queryKeys.universities.workflowByProgram;
export const workflowProgramsQueryKey = queryKeys.universities.workflowPrograms;
export const universityPassportQueryKey = queryKeys.universities.passport;

export class WorkflowApiError extends ApiRequestError {
  constructor(status: number, message: string, body?: unknown, transportMessage?: string) {
    super(status, body, message, transportMessage);
    this.name = 'WorkflowApiError';
  }
}

export interface WorkflowCommentApiRecord {
  id: string;
  instance_id: string;
  stage_id: string | null;
  author_keycloak_sub: string;
  author_name?: string | null;
  content: string;
  is_internal: boolean;
  question_status?: 'none' | 'open' | 'resolved';
  created_at: string;
  updated_at: string;
  attachments?: import('./workflow-attachments').WorkflowAttachmentApiRecord[];
  /** Frontend-only marker used while a create mutation is in flight. */
  is_optimistic?: boolean;
}

export function isWorkflowApiInstanceId(instanceId: string): boolean {
  return isMockDataSourceFor('workflow') || /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(instanceId);
}

export const isRealWorkflowMode = () => !isMockDataSourceFor('workflow');

export interface WorkflowPage<T> { items: T[]; page: number; page_size: number; total: number }

function unwrapApiResult<T>(result: Awaited<ReturnType<typeof apiFetch<T>>>): T {
  if (result.ok) return result.data;
  throw new WorkflowApiError(result.status, 'Не удалось выполнить действие Workflow.', result.body, result.error);
}

export async function listWorkflowComments(instanceId: string): Promise<WorkflowCommentApiRecord[]> {
  if (!isWorkflowApiInstanceId(instanceId)) return [];
  return fromDataSource({
    mock: () => mockListWorkflowComments(instanceId),
    real: async () => (await listWorkflowCommentsPage(instanceId, 1)).items,
    domain: 'workflow',
  });
}

export async function listWorkflowCommentsPage(instanceId: string, page: number): Promise<WorkflowPage<WorkflowCommentApiRecord>> {
  return unwrapApiResult(await apiFetch<WorkflowPage<WorkflowCommentApiRecord>>(`/api/v1/workflow/instances/${instanceId}/comments?page=${page}&page_size=100`));
}

export async function createWorkflowComment(instanceId: string, content: string, stageId?: string, files: File[] = [], isQuestion = false): Promise<WorkflowCommentApiRecord> {
  if (!isWorkflowApiInstanceId(instanceId)) throw new Error('Добавление комментариев недоступно для этого Workflow-источника.');
  if (files.length) {
    if (!isRealWorkflowMode()) throw new WorkflowApiError(0, 'Загрузка файлов доступна только при подключённом backend.');
    const { validateWorkflowUploadFile } = await import('./workflow-attachments');
    if (files.length > 10) throw new WorkflowApiError(0, 'Можно прикрепить не более 10 файлов.');
    for (const file of files) {
      const validation = validateWorkflowUploadFile(file);
      if (!validation.valid) throw new WorkflowApiError(0, validation.message);
    }
    const body = new FormData();
    body.append('content', content);
    body.append('is_question', String(isQuestion));
    if (stageId) body.append('stage_id', stageId);
    for (const file of files) body.append('files', file, file.name);
    const result = await apiUploadFormData<WorkflowCommentApiRecord>(`/api/v1/workflow/instances/${instanceId}/comments/with-attachments`, body);
    if (!result.ok) throw new WorkflowApiError(result.status, 'Не удалось сохранить комментарий с файлами.', result.body, result.error);
    return result.data;
  }
  return fromDataSource({
    mock: () => mockCreateWorkflowComment(instanceId, content, stageId),
    real: async () => unwrapApiResult(await apiFetch<WorkflowCommentApiRecord>(`/api/v1/workflow/instances/${instanceId}/comments`, { method: 'POST', body: { content, stage_id: stageId ?? null, is_question: isQuestion } })),
    domain: 'workflow',
  });
}

export interface WorkflowInstanceApiStage {
  id: string;
  responsible_id?: string | null;
  effective_responsible_id?: string | null;
  responsible_name?: string | null;
  responsible_email?: string | null;
  responsible_phone?: string | null;
  template_stage_id: string | null;
  order_index: number;
  name: string;
  description: string | null;
  is_required: boolean;
  status: string;
  due_date: string | null;
  started_at?: string | null;
  completed_at: string | null;
  is_overdue: boolean;
  days_overdue: number;
  tasks_total?: number;
  tasks_completed?: number;
}

export interface WorkflowInstanceApiRecord {
  id: string;
  university_id: string;
  template_id: string;
  program_id?: string | null;
  product_id?: string | null;
  university_name?: string | null;
  university_city?: string | null;
  program_name?: string | null;
  product_name?: string | null;
  responsible_name?: string | null;
  responsible_email?: string | null;
  responsible_phone?: string | null;
  current_stage_id: string | null;
  current_instance_stage_id: string | null;
  responsible_id: string | null;
  status: string;
  due_date: string | null;
  completed_at: string | null;
  is_overdue: boolean;
  days_overdue: number;
  stages: WorkflowInstanceApiStage[];
}

export async function getWorkflowInstance(instanceId: string): Promise<WorkflowInstanceApiRecord> {
  if (!isWorkflowApiInstanceId(instanceId)) throw new WorkflowApiError(0, 'Workflow instance имеет неверный идентификатор.');
  return fromDataSource({
    mock: () => mockGetWorkflowInstance(instanceId),
    real: async () => unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}`)),
    domain: 'workflow',
  });
}

export async function getWorkflowByProgram(universityId: string, programId: string): Promise<WorkflowInstanceApiRecord | null> {
  return fromDataSource({
    domain: 'workflow',
    mock: () => null,
    real: async () => unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord | null>(`/api/v1/workflow/instances/by-program/${encodeURIComponent(programId)}?university_id=${encodeURIComponent(universityId)}`)),
  });
}

export async function createProgramWorkflow(universityId: string, programId: string, templateId: string, productId?: string | null): Promise<WorkflowInstanceApiRecord> {
  return unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>('/api/v1/workflow/instances', {
    method: 'POST', body: { university_id: universityId, program_id: programId, template_id: templateId, ...(productId ? { product_id: productId } : {}) },
  }));
}

export async function archiveWorkflowInstance(instanceId: string): Promise<WorkflowInstanceApiRecord> {
  if (!isWorkflowApiInstanceId(instanceId)) throw new WorkflowApiError(0, 'Архивация недоступна для этого Workflow.');
  return unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}/archive`, { method: 'POST' }));
}

export async function completeWorkflowInstance(instanceId: string): Promise<WorkflowInstanceApiRecord> {
  return unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}/complete`, { method: 'POST' }));
}

export async function updateWorkflowResponsible(instanceId: string, responsibleId: string | null, replaceStageOverrides = false): Promise<WorkflowInstanceApiRecord> {
  return fromDataSource({
    domain: 'workflow',
    mock: async () => ({ ...mockGetWorkflowInstance(instanceId), responsible_id: responsibleId }),
    real: async () => unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}`, {
      method: 'PATCH', body: { responsible_id: responsibleId, replace_stage_overrides: replaceStageOverrides },
    })),
  });
}

export async function updateWorkflowStageResponsible(instanceId: string, stageId: string, responsibleId: string | null): Promise<WorkflowInstanceApiRecord> {
  if (!isWorkflowApiInstanceId(instanceId) || !isWorkflowApiInstanceId(stageId)) throw new WorkflowApiError(0, 'Изменение ответственного недоступно для этого Workflow.');
  return unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}/stages/${stageId}/responsible`, {
    method: 'PATCH', body: { responsible_id: responsibleId },
  }));
}

export async function updateWorkflowStageDueDate(instanceId: string, stageId: string, dueDate: string | null): Promise<WorkflowInstanceApiRecord> {
  if (!isWorkflowApiInstanceId(instanceId) || !isWorkflowApiInstanceId(stageId)) throw new WorkflowApiError(0, 'Изменение срока недоступно для этого Workflow.');
  return unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}/stages/${stageId}/due-date`, {
    method: 'PATCH', body: { due_date: dueDate },
  }));
}

export async function updateWorkflowStageName(instanceId: string, stageId: string, name: string): Promise<WorkflowInstanceApiRecord> {
  if (!isWorkflowApiInstanceId(instanceId) || !isWorkflowApiInstanceId(stageId)) throw new WorkflowApiError(0, 'Переименование недоступно для этого Workflow.');
  return unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}/stages/${stageId}/name`, {
    method: 'PATCH', body: { name },
  }));
}

export async function listWorkflowInstancePage(page: number, pageSize = 100): Promise<WorkflowPage<WorkflowInstanceApiRecord>> {
  return unwrapApiResult(await apiFetch<WorkflowPage<WorkflowInstanceApiRecord>>(`/api/v1/workflow/instances?page=${page}&page_size=${pageSize}`));
}

export interface WorkflowTaskApiRecord { id: string; instance_id: string; stage_id: string | null; title: string; status: string; responsible_id: string | null; deadline: string | null; completed_at: string | null }
export interface WorkflowAttachmentApiRecord { id: string; instance_id: string; stage_id: string | null; comment_id?: string | null; original_filename: string; mime_type: string; file_size: number; uploaded_by_keycloak_sub: string; uploaded_by_name?: string | null; created_at: string; updated_at: string }
export interface WorkflowTransitionApiRecord { id: string; instance_id: string; from_stage_id: string | null; to_stage_id: string | null; actor_keycloak_sub: string; comment: string; created_at: string }
export interface WorkflowActivityApiRecord { id: string; type: 'responsible_changed' | 'stage_responsible_changed' | 'deadline_changed' | 'stage_name_changed' | 'workflow_completed'; created_at: string; actor_name: string; stage_id?: string | null; stage_name: string; title: string }
export interface WorkflowAllowedApiRecord { id: string; name: string; order_index: number }

export async function listWorkflowTasksPage(instanceId: string, page: number): Promise<WorkflowPage<WorkflowTaskApiRecord>> {
  return unwrapApiResult(await apiFetch<WorkflowPage<WorkflowTaskApiRecord>>(`/api/v1/workflow/instances/${instanceId}/tasks?page=${page}&page_size=100`));
}
export async function createWorkflowTask(instanceId: string, stageId: string, title: string): Promise<WorkflowTaskApiRecord> {
  return unwrapApiResult(await apiFetch<WorkflowTaskApiRecord>(`/api/v1/workflow/instances/${instanceId}/tasks`, { method: 'POST', body: { stage_id: stageId, title } }));
}
export async function updateWorkflowTask(instanceId: string, taskId: string, patch: { title?: string; status?: 'open' | 'done' }): Promise<WorkflowTaskApiRecord> {
  return unwrapApiResult(await apiFetch<WorkflowTaskApiRecord>(`/api/v1/workflow/instances/${instanceId}/tasks/${taskId}`, { method: 'PATCH', body: patch }));
}
export async function deleteWorkflowTask(instanceId: string, taskId: string): Promise<void> {
  unwrapApiResult(await apiFetch<void>(`/api/v1/workflow/instances/${instanceId}/tasks/${taskId}`, { method: 'DELETE' }));
}
export async function listWorkflowAttachmentsPage(instanceId: string, page: number): Promise<WorkflowPage<WorkflowAttachmentApiRecord>> {
  return unwrapApiResult(await apiFetch<WorkflowPage<WorkflowAttachmentApiRecord>>(`/api/v1/workflow/instances/${instanceId}/attachments?page=${page}&page_size=100`));
}
export async function listWorkflowHistory(instanceId: string): Promise<WorkflowTransitionApiRecord[]> {
  return unwrapApiResult(await apiFetch<WorkflowTransitionApiRecord[]>(`/api/v1/workflow/instances/${instanceId}/transitions`));
}
export async function listWorkflowActivity(instanceId: string): Promise<WorkflowActivityApiRecord[]> {
  return unwrapApiResult(await apiFetch<WorkflowActivityApiRecord[]>(`/api/v1/workflow/instances/${instanceId}/activity`));
}
export async function getWorkflowAllowedTransitions(instanceId: string): Promise<WorkflowAllowedApiRecord[]> {
  return unwrapApiResult(await apiFetch<WorkflowAllowedApiRecord[]>(`/api/v1/workflow/instances/${instanceId}/allowed-transitions`));
}

export async function transitionWorkflowInstance(instanceId: string, targetInstanceStageId: string, comment: string, dueDate?: string): Promise<WorkflowInstanceApiRecord> {
  if (isRealWorkflowMode() && dueDate) throw new WorkflowApiError(0, 'Backend не поддерживает изменение дедлайна при переходе.');
  if (!isMockDataSource && !isWorkflowApiInstanceId(instanceId)) throw new WorkflowApiError(0, 'Переход недоступен для этого Workflow-источника.');
  return fromDataSource({
    mock: () => mockTransitionWorkflow(instanceId, targetInstanceStageId, comment),
    real: async () => unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}/transition`, { method: 'POST', body: { target_instance_stage_id: targetInstanceStageId, comment } })),
    domain: 'workflow',
  });
}

export async function getWorkflowRollbackTargets(instanceId: string): Promise<WorkflowAllowedApiRecord[]> {
  if (!isWorkflowApiInstanceId(instanceId)) return [];
  return fromDataSource({
    mock: async () => {
      const record = mockGetWorkflowInstance(instanceId);
      const current = record.current_instance_stage_id;
      const currentOrder = record.stages.find((stage) => stage.id === current)?.order_index ?? 0;
      return record.stages
        .filter((stage) => stage.order_index < currentOrder && (stage.status === 'completed' || stage.status === 'skipped'))
        .sort((left, right) => right.order_index - left.order_index)
        .map((stage) => ({ id: stage.id, name: stage.name, order_index: stage.order_index }));
    },
    real: async () => unwrapApiResult(await apiFetch<WorkflowAllowedApiRecord[]>(`/api/v1/workflow/instances/${instanceId}/rollback-targets`)),
    domain: 'workflow',
  });
}

export async function rollbackWorkflowInstance(instanceId: string, targetInstanceStageId: string, comment: string): Promise<WorkflowInstanceApiRecord> {
  if (!isMockDataSource && !isWorkflowApiInstanceId(instanceId)) throw new WorkflowApiError(0, 'Откат недоступен для этого Workflow-источника.');
  return fromDataSource({
    mock: () => mockRollbackWorkflow(instanceId, targetInstanceStageId, comment),
    real: async () => unwrapApiResult(await apiFetch<WorkflowInstanceApiRecord>(`/api/v1/workflow/instances/${instanceId}/rollback`, { method: 'POST', body: { target_instance_stage_id: targetInstanceStageId, comment } })),
    domain: 'workflow',
  });
}

export async function editWorkflowComment(commentId: string, content: string): Promise<WorkflowCommentApiRecord> {
  return fromDataSource({
    mock: () => mockEditWorkflowComment(commentId, content),
    real: async () => unwrapApiResult(await apiFetch<WorkflowCommentApiRecord>(`/api/v1/workflow/comments/${commentId}`, { method: 'PATCH', body: { content } })),
    domain: 'workflow',
  });
}

export async function updateWorkflowQuestionStatus(commentId: string, status: 'none' | 'open' | 'resolved'): Promise<WorkflowCommentApiRecord> {
  return unwrapApiResult(await apiFetch<WorkflowCommentApiRecord>(`/api/v1/workflow/comments/${encodeURIComponent(commentId)}/question-status`, { method: 'PATCH', body: { status } }));
}

export interface MeetingAgenda {
  university_id: string;
  university_name: string;
  city: string | null;
  instance_id: string;
  stage_id: string;
  stage_name: string;
  stage_order: number;
  generated_at: string;
  as_of: string;
  expires_through: string;
  warning_days: number;
  programs: { items: { program_id: string; name: string; direction: string; status: 'active' | 'launched'; launch_date: string | null }[]; total: number; omitted: number };
  expiring_licenses: { items: { license_id: string; license_number: string; product: string; expires_at: string; days_left: number }[]; total: number; omitted: number };
  open_questions: { items: { comment_id: string; instance_id: string; stage_id: string | null; author_keycloak_sub?: string | null; content: string; created_at: string }[]; total: number; omitted: number };
}

export const meetingAgendaQueryKey = (instanceId: string) => [...workflowQueryKey(instanceId), 'meeting-agenda'] as const;

// Runtime stage names are the only meeting indicator in configurable templates.
export function isMeetingAgendaStage(templateStageId: string | null | undefined, name: string): boolean {
  return Boolean(templateStageId) && /(?<![\p{L}\p{N}_])встреч(?:а|и|у|е|ей)(?![\p{L}\p{N}_])/iu.test(name);
}

export async function getMeetingAgenda(instanceId: string, signal?: AbortSignal, stageId?: string): Promise<MeetingAgenda> {
  return unwrapApiResult(await apiFetch<MeetingAgenda>(`/api/v1/workflow/instances/${encodeURIComponent(instanceId)}/meeting-agenda${stageId ? `?stage_id=${encodeURIComponent(stageId)}` : ''}`, { signal }));
}

export async function downloadMeetingAgenda(instanceId: string, stageId?: string): Promise<Blob> {
  return unwrapApiResult(await apiDownload(`/api/v1/workflow/instances/${encodeURIComponent(instanceId)}/meeting-agenda.pdf${stageId ? `?stage_id=${encodeURIComponent(stageId)}` : ''}`));
}

export async function deleteWorkflowComment(commentId: string): Promise<void> {
  unwrapApiResult(await apiFetch<void>(`/api/v1/workflow/comments/${commentId}`, { method: 'DELETE' }));
}

export function workflowAttachmentDownloadUrl(instanceId: string, attachmentId: string): string | null {
  return isMockDataSourceFor('workflow') ? `data:text/plain;charset=utf-8,Mock%20attachment%20${encodeURIComponent(attachmentId)}` : null;
}

export async function downloadWorkflowAttachment(instanceId: string, attachmentId: string): Promise<Blob> {
  if (!isWorkflowApiInstanceId(instanceId)) throw new WorkflowApiError(0, 'Некорректный идентификатор Workflow.');
  return unwrapApiResult(await apiDownload(`/api/v1/workflow/instances/${instanceId}/attachments/${attachmentId}/download`));
}

export async function deleteWorkflowAttachment(instanceId: string, attachmentId: string): Promise<void> {
  if (!isWorkflowApiInstanceId(instanceId)) throw new Error('Удаление вложений недоступно для этого Workflow-источника.');
  await fromDataSource({
    mock: () => undefined,
    real: async () => unwrapApiResult(await apiFetch<void>(`/api/v1/workflow/instances/${instanceId}/attachments/${attachmentId}`, { method: 'DELETE' })),
    domain: 'workflow',
  });
}

const workflowStageNames = [
  'Инициация проекта',
  'Сбор данных о вузе',
  'Проверка договорных условий',
  'Подготовка дорожной карты',
  'Согласование программы',
  'Подготовка преподавателей',
  'Подготовка инфраструктуры',
  'Подписание документов',
  'Настройка LMS',
  'Пилотный запуск',
  'Сопровождение запуска',
  'Анализ результатов',
  'Итоговая отчётность',
  'Завершение проекта',
] as const;

const workflowStageIndex: Record<UniversityStage['id'], number> = { preparation: 3, launch: 6, support: 10, completed: 13 };

function getWorkflowStageStatus(index: number, currentIndex: number, attention: boolean, numericId: number): UniversityWorkflowStageStatus {
  if (currentIndex >= workflowStageNames.length - 1) {
    if (index < currentIndex) return index === 2 && numericId % 2 === 0 ? 'skipped' : 'completed';
    if (index === currentIndex) return 'completed';
    return 'pending';
  }
  if (index === currentIndex && currentIndex < workflowStageNames.length - 1) return 'current';
  if (index < currentIndex) return index === 2 && numericId % 2 === 0 ? 'skipped' : 'completed';
  if (index === currentIndex + 1 && attention) return 'pending';
  return 'pending';
}

function getWorkflowDeadline(index: number, status: UniversityWorkflowStageStatus): string {
  if (status === 'overdue') return '2026-09-18';
  if (status === 'current') return '2026-09-30';
  if (status === 'pending') return index % 3 === 0 ? '2026-09-25' : `2026-10-${String(1 + (index % 9)).padStart(2, '0')}`;
  return `2026-09-${String(Math.max(2, 20 - (13 - index) * 2)).padStart(2, '0')}`;
}

function getWorkflowStageDates(index: number, status: UniversityWorkflowStageStatus): Pick<UniversityWorkflowStage, 'startedAt' | 'completedAt' | 'completion'> {
  if (status === 'pending') return { startedAt: null, completedAt: null, completion: null };
  const startedAt = `2026-09-${String(Math.max(2, 4 + index)).padStart(2, '0')}T09:15:00+03:00`;
  if (status === 'completed' || status === 'skipped') {
    const completedAt = `2026-09-${String(Math.max(3, 8 + index)).padStart(2, '0')}T16:20:00+03:00`;
    return { startedAt, completedAt, completion: index % 4 === 0 ? 'late' : 'on_time' };
  }
  return { startedAt, completedAt: null, completion: null };
}

function getWorkflowComments(id: string, index: number, responsible: UniversityResponsible | null): UniversityWorkflowComment[] {
  const author = responsible?.name ?? 'Анна Иванова';
  return [
    { id: `${id}-stage-${index + 1}-comment-1`, author: 'Система Workflow', authorId: 'system', authorRole: 'Система', isSystem: true, occurredAt: '2026-09-20T11:30:00+03:00', updatedAt: '2026-09-20T11:30:00+03:00', text: index === 10 ? 'Зафиксировали контрольные точки запуска и ответственных.' : 'Обновили материалы этапа и подтвердили следующий шаг.' },
    { id: `${id}-stage-${index + 1}-comment-2`, author: 'Борис Петров', authorId: 'responsible-boris', authorRole: 'Менеджер', occurredAt: '2026-09-18T16:10:00+03:00', updatedAt: '2026-09-18T16:10:00+03:00', text: 'Проверили комплект данных со стороны вуза.' },
    { id: `${id}-stage-${index + 1}-comment-3`, author: 'Елена Смирнова', authorId: 'responsible-elena', authorRole: 'Координатор программы', occurredAt: '2026-09-16T13:45:00+03:00', updatedAt: '2026-09-16T13:45:00+03:00', text: 'Добавили комментарий методиста к этапу.' },
    { id: `${id}-stage-${index + 1}-comment-4`, author: author || 'Анна Иванова', authorId: responsible?.id ?? '1', authorRole: responsible?.role ?? 'Администратор', occurredAt: '2026-09-12T15:00:00+03:00', updatedAt: '2026-09-12T15:00:00+03:00', text: 'Согласовали план ближайших запусков.' },
  ];
}

/** Typed frontend adapter for the future GET /universities/{id}/workflow endpoint. */
async function getMockUniversityWorkflow(id: string): Promise<UniversityWorkflow> {
  if (!hasUniversityContext(id)) return getApiUniversityWorkflow(mockGetWorkflowInstance(id));
  const university = getUniversityOrThrow(id);
  const assignedResponsible = assignedMockResponsible(id);
  const currentResponsible = assignedResponsible === undefined ? university.responsible : assignedResponsible;
  const numericId = getUniversityNumericId(id);
  const storedStageId = getMockWorkflowCurrentStageId(id);
  const storedStageIndex = storedStageId ? workflowStageNames.findIndex((_name, index) => `${id}-workflow-stage-${index + 1}` === storedStageId) : -1;
  const currentIndex = storedStageIndex >= 0 ? storedStageIndex : workflowStageIndex[university.currentStage.id] ?? 3;
  const stages = workflowStageNames.map((name, index) => {
    const status = getWorkflowStageStatus(index, currentIndex, university.attention, numericId);
    const previousStatus = index === 0 ? 'pending' : getWorkflowStageStatus(index - 1, currentIndex, university.attention, numericId);
    const attachments: UniversityWorkflowAttachment[] = index % 3 === 0
      ? [{ id: `${id}-stage-${index + 1}-attachment`, fileName: index === 6 ? 'дорожная-карта-запуска.pdf' : 'материалы-этапа.docx', fileType: index === 6 ? 'PDF' : 'DOCX', fileSize: index === 6 ? '1,8 МБ' : '420 КБ', mimeType: index === 6 ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', fileSizeBytes: index === 6 ? 1_887_436 : 430_080, uploadedBy: university.responsible, uploadedAt: '2026-09-20T11:30:00+03:00', description: index === 6 ? 'Актуальная версия дорожной карты запуска.' : undefined }]
      : [];
    const tasks: UniversityWorkflowTask[] = [
      { id: `${id}-stage-${index + 1}-task-1`, label: 'Проверить входные данные', completed: status === 'completed' || status === 'skipped' },
      { id: `${id}-stage-${index + 1}-task-2`, label: 'Подтвердить результат этапа', completed: status === 'completed' },
      { id: `${id}-stage-${index + 1}-task-3`, label: 'Назначить следующий шаг', completed: index < currentIndex },
    ];
    return {
      id: `${id}-workflow-stage-${index + 1}`,
      orderIndex: index + 1,
      name,
      status,
      deadline: getWorkflowDeadline(index, status),
      ...getWorkflowStageDates(index, status),
      responsible: currentResponsible,
      comments: getWorkflowComments(id, index, currentResponsible),
      attachments,
      tasks,
      transitions: index === 0 || status === 'pending' ? [] : [{
        id: `${id}-stage-${index + 1}-transition`,
        occurredAt: `2026-09-${String(Math.max(4, 20 - index)).padStart(2, '0')}T13:45:00+03:00`,
        actor: university.responsible?.name ?? 'Анна Иванова',
        fromStatus: previousStatus,
        toStatus: status,
        comment: status === 'skipped' ? 'Этап пропущен по согласованному плану.' : 'Этап переведён после проверки результата.',
      }],
    } satisfies UniversityWorkflowStage;
  });

  const currentStage = stages.find((stage) => stage.status === 'current') ?? stages.find((stage) => stage.orderIndex === currentIndex + 1) ?? null;
  registerMockWorkflow({
    instanceId: id,
    universityId: university.id,
    universityName: university.name,
    currentStageId: currentStage?.id ?? stages[0].id,
    stages: stages.map((workflowStage) => ({
      id: workflowStage.id,
      name: workflowStage.name,
      orderIndex: workflowStage.orderIndex,
      isRequired: true,
    })),
  });
  return {
    templateId: 'mock-university-workflow',
    universityId: university.id,
    universityName: university.name,
    universityCity: university.city,
    workflowName: 'Подключение университета',
    responsibleId: null,
    responsibleName: currentResponsible?.name ?? null,
    responsibleEmail: currentResponsible?.email ?? null,
    responsiblePhone: null,
    currentStage,
    completedSteps: stages.filter((stage) => stage.status === 'completed').length,
    totalSteps: stages.length,
    stages,
  };
}

export async function getUniversityWorkflow(id: string): Promise<UniversityWorkflow> {
  return fromDataSource({
    domain: 'workflow',
    mock: () => getMockUniversityWorkflow(id),
    real: async () => getApiUniversityWorkflow(await getWorkflowInstance(id)),
  });
}

export function getApiUniversityWorkflow(instance: WorkflowInstanceApiRecord): UniversityWorkflow {
  const stages = instance.stages.map((stage): UniversityWorkflowStage => {
    const isCurrent = stage.id === instance.current_instance_stage_id;
    const status: UniversityWorkflowStageStatus = stage.status === 'completed' || stage.status === 'skipped'
      ? stage.status
      : isCurrent ? stage.is_overdue ? 'overdue' : 'current' : 'pending';
    return {
      id: stage.id,
      templateStageId: stage.template_stage_id,
      orderIndex: stage.order_index,
      name: stage.name,
      status,
      deadline: stage.due_date ?? '',
      startedAt: stage.started_at ?? null,
      completedAt: stage.completed_at,
      completion: stage.completed_at && stage.due_date && stage.completed_at.slice(0, 10) > stage.due_date ? 'late' : stage.completed_at ? 'on_time' : null,
      isOptional: !stage.is_required,
      responsible: (stage.effective_responsible_id ?? instance.responsible_id) && (stage.responsible_name ?? instance.responsible_name) ? { id: (stage.effective_responsible_id ?? instance.responsible_id)!, name: (stage.responsible_name ?? instance.responsible_name)!, email: stage.responsible_email ?? instance.responsible_email ?? undefined } : null,
      responsibleOverrideId: stage.responsible_id ?? null,
      comments: [],
      attachments: [],
      tasks: [],
      taskTotal: stage.tasks_total ?? 0,
      taskCompleted: stage.tasks_completed ?? 0,
      transitions: [],
    };
  });
  const currentStage = stages.find((stage) => stage.id === instance.current_instance_stage_id) ?? null;
  return {
    templateId: instance.template_id,
    status: instance.status,
    universityId: instance.university_id,
    universityName: instance.university_name ?? 'Workflow',
    universityCity: instance.university_city ?? '',
    programId: instance.program_id ?? null,
    workflowName: instance.program_name ?? 'Workflow',
    responsibleId: instance.responsible_id ?? null,
    responsibleName: instance.responsible_name ?? null,
    responsibleEmail: instance.responsible_email ?? null,
    responsiblePhone: instance.responsible_phone ?? null,
    currentStage,
    completedSteps: stages.filter((stage) => stage.status === 'completed' || stage.status === 'skipped').length,
    totalSteps: stages.length,
    stages,
  };
}

export type UniversityHistoryEventType = 'workflow' | 'document' | 'meeting' | 'note' | 'audit';

export interface UniversityHistoryEvent {
  id: string;
  occurredAt: string;
  type: UniversityHistoryEventType;
  user: UniversityResponsible;
  action: string;
  details: string;
  entity: { id: string; label: string };
  oldValues?: Record<string, string | number | null>;
  newValues?: Record<string, string | number | null>;
  ip?: string;
  userAgent?: string;
  auditEvent?: import('./audit-repository').AuditEvent;
  attachment?: { instanceId: string; id: string; fileName: string; mimeType?: string };
}

export interface UniversityHistoryFilters {
  type: UniversityHistoryEventType | 'all';
  dateFrom: string;
  dateTo: string;
  userId: string;
  entityId: string;
}

export interface UniversityHistoryFilterOptions {
  users: UniversityResponsible[];
  entities: Array<{ id: string; label: string }>;
}

export const universityHistoryFamilyQueryKey = queryKeys.universities.historyFamily;
export const universityHistoryQueryKey = queryKeys.universities.history;

const historyEvents = (id: string, university: UniversityListItem): UniversityHistoryEvent[] => {
  const anna = responsible.anna;
  const boris = responsible.boris;
  const currentStageName = university.currentStage.name;
  const assignment = getMockResponsibleAssignment(id);
  const assigned = assignedMockResponsible(id);
  return [
    ...(assignment && assigned ? [{ id: `${id}-responsible-assignment-${assignment.assignedAt}`, occurredAt: assignment.assignedAt, type: 'audit' as const, user: anna, action: 'Изменён ответственный', details: assignment.reason ? `Новый ответственный: ${assigned.name}. Причина: ${assignment.reason}` : `Новый ответственный: ${assigned.name}.`, entity: { id: `${id}-responsible`, label: 'Ответственный ВУЗа' }, oldValues: { responsible: university.responsible?.name ?? null }, newValues: { responsible: assigned.name }, ip: 'mock', userAgent: 'CRM demo' }] : []),
    { id: `${id}-history-2`, occurredAt: '2026-09-19T15:20:00+03:00', type: 'audit', user: boris, action: 'Изменён срок этапа', details: `${currentStageName} → новый срок 30 сент. 2026 г.`, entity: { id: `${id}-workflow-stage-11`, label: currentStageName }, oldValues: { deadline: '2026-09-18', status: 'attention' }, newValues: { deadline: '2026-09-30', status: 'current' }, ip: '10.24.18.42', userAgent: 'Chrome 128 · macOS' },
    { id: `${id}-history-4`, occurredAt: '2026-09-17T10:05:00+03:00', type: 'workflow', user: anna, action: 'Этап завершён', details: 'Подготовка преподавателей → Подготовка инфраструктуры', entity: { id: `${id}-workflow-stage-7`, label: 'Подготовка инфраструктуры' } },
    { id: `${id}-history-5`, occurredAt: '2026-09-16T13:45:00+03:00', type: 'note', user: { id: 'responsible-elena', name: 'Елена Смирнова' }, action: 'Добавлена заметка', details: 'Нужно подтвердить готовность аудитории к пилоту.', entity: { id: `${id}-note-1`, label: 'Подготовка к пилоту' } },
    { id: `${id}-history-6`, occurredAt: '2026-09-15T09:30:00+03:00', type: 'audit', user: anna, action: 'Изменён ответственный', details: 'Ответственный обновлён в карточке Workflow', entity: { id: `${id}-workflow-stage-10`, label: 'Пилотный запуск' }, oldValues: { responsible: 'Борис Петров' }, newValues: { responsible: anna.name }, ip: '10.24.18.42', userAgent: 'Chrome 128 · macOS' },
    { id: `${id}-history-9`, occurredAt: '2026-09-09T17:10:00+03:00', type: 'workflow', user: boris, action: 'Этап изменён', details: `Текущий этап: ${currentStageName}`, entity: { id: `${id}-workflow-stage-11`, label: currentStageName } },
    { id: `${id}-history-10`, occurredAt: '2026-09-06T14:35:00+03:00', type: 'note', user: anna, action: 'Добавлена заметка', details: 'Обновили план подготовки преподавателей.', entity: { id: `${id}-note-2`, label: 'План подготовки преподавателей' } },
  ];
};

export function getUniversityHistoryFilterOptions(id: string): UniversityHistoryFilterOptions {
  if (!isMockDataSourceFor('passport')) return { users: [], entities: [] };
  const university = getUniversityOrThrow(id);
  const events = historyEvents(id, university);
  return {
    users: [...new Map(events.map((event) => [event.user.id, event.user])).values()].sort((left, right) => left.name.localeCompare(right.name, 'ru')),
    entities: [...new Map(events.map((event) => [event.entity.id, event.entity])).values()].sort((left, right) => left.label.localeCompare(right.label, 'ru')),
  };
}

/** Typed frontend adapter for the future GET /universities/{id}/history endpoint. */
async function getMockUniversityHistory(id: string, filters: UniversityHistoryFilters): Promise<UniversityHistoryEvent[]> {
  const university = getUniversityOrThrow(id);
  return historyEvents(id, university).filter((event) => {
    const date = event.occurredAt.slice(0, 10);
    if (filters.type !== 'all' && event.type !== filters.type) return false;
    if (filters.dateFrom && date < filters.dateFrom) return false;
    if (filters.dateTo && date > filters.dateTo) return false;
    if (filters.userId && event.user.id !== filters.userId) return false;
    if (filters.entityId && event.entity.id !== filters.entityId) return false;
    return true;
  });
}

export async function getUniversityHistory(id: string, filters: UniversityHistoryFilters): Promise<UniversityHistoryEvent[]> {
  return fromDataSource({ domain: 'passport', mock: () => getMockUniversityHistory(id, filters), real: () => realGetUniversityHistory(id, filters) });
}


export interface UniversityProgramRow {
  id: string;
  direction: string;
  name: string;
  status: ProgramStatus;
  launchDate: string;
  responsible: UniversityResponsible | null;
}



export type UniversityProductStatus = 'planned' | 'active' | 'expiring' | 'expired';

export interface UniversityProductRow {
  id: string;
  name: string;
  version: string;
  vendor: string;
  status: UniversityProductStatus;
  licenseNumber: string;
  expiresAt: string;
}

export const universityProgramsQueryKey = queryKeys.universities.programs;
export const universityProductsQueryKey = queryKeys.universities.products;

const programDirections = ['Аналитика и данные', 'Цифровая трансформация', 'Информационная безопасность', 'Управление проектами'];
/** Shared catalog dictionary used by university passport and report filters. */
export const universityProgramDirectionOptions = programDirections.map((name) => ({ id: name.toLocaleLowerCase('ru-RU').replace(/\s+/g, '-'), name }));
const programNames = ['Аналитика данных', 'Цифровая экономика', 'Кибербезопасность', 'ИТ-менеджмент'];

function getUniversityNumericId(id: string): number {
  const mockSuffix = id.match(/(?:^|-)0*(\d{1,4})$/)?.[1];
  if (mockSuffix) return Math.max(1, Number(mockSuffix));
  return [...id].reduce((hash, character) => (hash * 31 + character.charCodeAt(0)) % 97, 0) + 1;
}

function getUniversityOrThrow(id: string): UniversityListItem {
  const university = universitiesWithRelationships.find((item) => item.id === id) ?? observedUniversities.get(id);
  if (!university) throw new Error('Университет не найден');
  if (university.availability) {
    return {
      ...university,
      programsCount: university.availability.programs ? university.programsCount : 4,
      programStatusCounts: university.availability.programs ? university.programStatusCounts : programCounts(1, 2, 1),
      currentStage: university.availability.stage ? university.currentStage : stage.preparation,
    };
  }
  return university;
}

function hasUniversityContext(id: string): boolean {
  return universitiesWithRelationships.some((item) => item.id === id) || observedUniversities.has(id);
}

/** Typed frontend adapter for the future university programs endpoint. */
async function getMockUniversityPrograms(id: string): Promise<UniversityProgramRow[]> {
  const university = getUniversityOrThrow(id);
  const numericId = getUniversityNumericId(id);
  const statuses: ProgramStatus[] = ['active', 'launched', 'planned', 'archived', 'active', 'launched'];
  const count = Math.min(8, Math.max(4, university.programsCount));

  return Array.from({ length: count }, (_, index) => ({
    id: `${id}-program-${index + 1}`,
    direction: programDirections[(index + numericId) % programDirections.length],
    name: programNames[(index + numericId) % programNames.length],
    status: statuses[(index + numericId) % statuses.length],
    launchDate: `2026-${String(((index + numericId) % 9) + 1).padStart(2, '0')}-${String(((index * 3 + numericId) % 20) + 1).padStart(2, '0')}`,
    responsible: university.responsible,
  }));
}

export async function getUniversityPrograms(id: string, page = 1, pageSize = 20, signal?: AbortSignal, status: ProgramStatus | 'all' = 'all'): Promise<PaginatedResult<UniversityProgramRow>> {
  return fromDataSource({ domain: 'passport', signal, mock: async () => {
    const items = (await getMockUniversityPrograms(id)).filter((item) => status === 'all' || item.status === status);
    return { items: items.slice((page - 1) * pageSize, page * pageSize), page, pageSize, total: items.length };
  }, real: () => realGetUniversityPrograms(id, page, pageSize, signal, status) });
}

export async function getWorkflowSelectorPrograms(id: string, signal?: AbortSignal): Promise<UniversityProgramRow[]> {
  const first = await getUniversityPrograms(id, 1, 100, signal);
  const items = [...first.items];
  for (let page = 2; items.length < first.total; page += 1) {
    const next = await getUniversityPrograms(id, page, 100, signal);
    if (!next.items.length) break;
    items.push(...next.items);
  }
  return items;
}



export async function attachUniversityProgram(universityId: string, programId: string): Promise<{ id: string }> {
  return unwrapPassportMutation(await apiFetch<{ id: string }>(`/api/v1/universities/${encodeURIComponent(universityId)}/programs`, {
    method: 'POST',
    body: { program_id: programId, status: 'planned' },
  }));
}

export async function attachUniversityProduct(universityId: string, productId: string): Promise<{ id: string }> {
  return unwrapPassportMutation(await apiFetch<{ id: string }>(`/api/v1/universities/${encodeURIComponent(universityId)}/products`, {
    method: 'POST',
    body: { product_id: productId, status: 'planned' },
  }));
}

function unwrapPassportMutation<T>(result: Awaited<ReturnType<typeof apiFetch<T>>>): T {
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, 'Не удалось сохранить данные паспорта.', result.error);
}


/** Typed frontend adapter for the future university products/licenses endpoint. */
async function getMockUniversityProducts(id: string): Promise<UniversityProductRow[]> {
  const university = getUniversityOrThrow(id);
  const numericId = getUniversityNumericId(id);
  const statuses: UniversityProductStatus[] = ['active', 'expiring', 'active', 'expired', 'active'];
  const names = ['Профессиональная переподготовка', 'Короткие курсы', 'Корпоративный трек', 'Виртуальный кампус', 'Система тестирования'];
  const vendors = ['Ростелеком', 'Яндекс Практикум', 'Skillbox', 'Контур', 'Ростелеком'];

  return names.map((name, index) => ({
    id: `${id}-product-${index + 1}`,
    name,
    version: `v${index + 1}.${(numericId + index) % 5}`,
    vendor: vendors[index],
    status: statuses[(index + numericId) % statuses.length],
    licenseNumber: `LIC-${String(numericId).padStart(3, '0')}-${String(index + 1).padStart(3, '0')}`,
    expiresAt: `202${index % 2 === 0 ? '7' : '6'}-${String(((index + numericId) % 9) + 1).padStart(2, '0')}-15`,
  })).filter((_, index) => university.productIds ? index < 3 + (numericId % 3) : index < 2);
}

export async function getUniversityProducts(id: string, queryClient?: QueryClient): Promise<UniversityProductRow[]> {
  return fromDataSource({ domain: 'passport', mock: () => getMockUniversityProducts(id), real: () => realGetUniversityProducts(id, queryClient) });
}

export type UniversityLicenseStatus = 'active' | 'expires_soon' | 'expired';

export interface UniversityLicenseRow {
  id: string;
  product: string;
  vendor: string;
  licenseNumber: string;
  signedAt: string;
  expiresAt: string;
  status: UniversityLicenseStatus;
  transfer: string;
  contract: string;
}

export type UniversityDocumentStatus = 'signed' | 'pending' | 'expired' | 'archived';

export interface UniversityDocumentRow {
  id: string;
  type: string;
  name: string;
  fileName: string;
  hasFile: boolean;
  fileSize: string;
  signedAt: string | null;
  expiresAt: string | null;
  status: UniversityDocumentStatus;
  uploadedBy: string;
  uploadedAt: string;
  downloadUrl?: string;
}

export type UniversityMeetingType = 'online' | 'offline' | 'phone' | 'email';

export interface UniversityMeetingParticipant {
  id: string;
  name: string;
  initials: string;
}

export interface UniversityMeetingRow {
  id: string;
  occurredAt: string | null;
  type: UniversityMeetingType | null;
  subject: string;
  participants: UniversityMeetingParticipant[];
  outcome: string;
  nextAction: string;
  dueDate: string | null;
  author: string;
  workflowInstanceId?: string | null;
  workflowStageId?: string | null;
  workflowStageName?: string | null;
}

export interface UniversityMeetingInput {
  type: UniversityMeetingType;
  subject: string;
  meetingAt: string;
  participants: string[];
  outcome: string;
  nextAction: string;
  dueDate: string;
}

export interface UniversityResponsibleContact {
  id: string;
  name: string;
  role: string;
  email: string;
  phone: string;
  isPrimary: boolean;
  initials: string;
}

export const universityLicensesQueryKey = queryKeys.universities.licenses;
export const universityDocumentsQueryKey = queryKeys.universities.documents;
export const universityDocumentsPageQueryKey = (id: string, page: number, search: string, type: string, status: string) => [...universityDocumentsQueryKey(id), page, search, type, status] as const;
export const universityMeetingsQueryKey = queryKeys.universities.meetings;
export const universityResponsiblesQueryKey = queryKeys.universities.responsibles;

/** Typed frontend adapter for the future university licenses endpoint. */
async function getMockUniversityLicenses(id: string): Promise<UniversityLicenseRow[]> {
  const university = getUniversityOrThrow(id);
  const numericId = getUniversityNumericId(id);
  const statuses: UniversityLicenseStatus[] = ['expires_soon', 'active', 'expired', 'active', 'expires_soon'];
  const products = ['Профессиональная переподготовка', 'Короткие курсы', 'Корпоративный трек', 'Виртуальный кампус', 'Система тестирования'];
  const vendors = ['Ростелеком', 'Яндекс Практикум', 'Skillbox', 'Контур', 'Ростелеком'];
  return products.map((product, index) => {
    const status = statuses[(index + numericId) % statuses.length];
    return {
      id: `${id}-license-${index + 1}`,
      product,
      vendor: vendors[index],
      licenseNumber: `LIC-${String(numericId).padStart(3, '0')}-${String(index + 1).padStart(3, '0')}`,
      signedAt: `2026-0${((index + numericId) % 8) + 1}-05`,
      expiresAt: status === 'expired' ? '2026-08-15' : status === 'expires_soon' ? '2026-10-15' : `2027-0${(index % 6) + 1}-15`,
      status,
      transfer: index % 2 === 0 ? 'Допустима' : 'Не требуется',
      contract: `Договор № ${numericId}-${String(index + 12).padStart(3, '0')}`,
    };
  }).filter((_, index) => university.productIds ? index < 3 + (numericId % 3) : index < 2);
}

export async function getUniversityLicenses(id: string, queryClient?: QueryClient): Promise<UniversityLicenseRow[]> {
  return fromDataSource({ domain: 'passport', mock: () => getMockUniversityLicenses(id), real: () => realGetUniversityLicenses(id, queryClient) });
}

export async function getUniversityDocuments(id: string, page = 1, pageSize = 20, search = '', type = 'all', status = 'all', signal?: AbortSignal): Promise<PaginatedResult<UniversityDocumentRow> & { types: string[] }> {
  return realGetUniversityDocuments(id, page, pageSize, search, type, status, signal);
}

export async function downloadUniversityDocument(universityId: string, documentId: string): Promise<Blob> {
  return unwrapApiResult(await apiDownload(`/api/v1/universities/${encodeURIComponent(universityId)}/passport/documents/${encodeURIComponent(documentId)}/download`));
}

export type UniversityDocumentType = 'contract' | 'license' | 'act' | 'protocol' | 'other';

export async function createUniversityDocument(universityId: string, input: { type: UniversityDocumentType; title: string; file: File }): Promise<void> {
  const body = new FormData();
  body.append('document_type', input.type);
  body.append('title', input.title);
  body.append('file', input.file, input.file.name);
  unwrapApiResult(await apiUploadFormData(`/api/v1/universities/${encodeURIComponent(universityId)}/passport/documents`, body));
}

/** Typed frontend adapter for the future university meetings endpoint. */
export async function getUniversityMeetings(id: string, page = 1, pageSize = 20, signal?: AbortSignal): Promise<PaginatedResult<UniversityMeetingRow>> {
  return realGetUniversityMeetings(id, page, pageSize, signal);
}

export async function createUniversityMeeting(universityId: string, input: UniversityMeetingInput): Promise<{ id: string }> {
  return unwrapPassportMutation(await apiFetch<{ id: string }>(`/api/v1/universities/${encodeURIComponent(universityId)}/meetings`, {
    method: 'POST',
    body: { meeting_type: input.type, subject: input.subject.trim(), meeting_at: input.meetingAt, participants: input.participants.map((name) => ({ name })), outcome: input.outcome.trim() || null, next_action: input.nextAction.trim() || null, next_action_due: input.dueDate || null },
  }));
}

export async function updateUniversityMeeting(meetingId: string, input: UniversityMeetingInput): Promise<{ id: string }> {
  return unwrapPassportMutation(await apiFetch<{ id: string }>(`/api/v1/meetings/${encodeURIComponent(meetingId)}`, {
    method: 'PATCH',
    body: { meeting_type: input.type, subject: input.subject.trim(), meeting_at: input.meetingAt, participants: input.participants.map((name) => ({ name })), outcome: input.outcome.trim() || null, next_action: input.nextAction.trim() || null, next_action_due: input.dueDate || null },
  }));
}

export async function deleteUniversityMeeting(meetingId: string): Promise<void> {
  unwrapPassportMutation(await apiFetch<void>(`/api/v1/meetings/${encodeURIComponent(meetingId)}`, { method: 'DELETE' }));
}

/** Typed frontend adapter for the future university responsibles endpoint. */
async function getMockUniversityResponsibles(id: string): Promise<UniversityResponsibleContact[]> {
  const university = getUniversityOrThrow(id);
  const assignedResponsible = assignedMockResponsible(id);
  const contacts: UniversityResponsibleContact[] = [
    { id: 'contact-anna', name: 'Анна Иванова', role: 'Координатор проекта', email: 'anna.ivanova@example.ru', phone: '+7 (900) 123-45-67', isPrimary: true, initials: 'АИ' },
    { id: 'contact-boris', name: 'Борис Петров', role: 'Руководитель направления', email: 'boris.petrov@example.ru', phone: '+7 (900) 234-56-78', isPrimary: false, initials: 'БП' },
    { id: 'contact-elena', name: 'Елена Смирнова', role: 'Методист', email: 'elena.smirnova@example.ru', phone: '+7 (900) 345-67-89', isPrimary: false, initials: 'ЕС' },
  ];
  const primary = assignedResponsible === undefined ? university.responsible : assignedResponsible;
  if (primary) {
    const matchingIndex = contacts.findIndex((contact) => contact.email === primary.email || contact.name === primary.name);
    if (matchingIndex >= 0) {
      contacts.forEach((contact, index) => { contact.isPrimary = index === matchingIndex; });
    } else {
      contacts[0] = { ...contacts[0], id: primary.id, name: primary.name, role: primary.role ?? contacts[0].role, email: primary.email ?? contacts[0].email, initials: primary.name.split(' ').map((part) => part[0]).join('').slice(0, 2).toLocaleUpperCase('ru-RU') };
    }
  }
  return contacts;
}

export async function getUniversityResponsibles(id: string, queryClient?: QueryClient): Promise<UniversityResponsibleContact[]> {
  return fromDataSource({ domain: 'passport', mock: () => getMockUniversityResponsibles(id), real: () => realGetUniversityResponsibles(id, queryClient) });
}
