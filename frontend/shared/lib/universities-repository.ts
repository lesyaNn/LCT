import { getHealthStatus, type HealthStatus } from './health-score';
import { programStatusLabels, type ProgramStatus } from './dashboard-repository';
import { getExpirationStatus, type ExpirationStatus } from './formatters';

export type { ProgramStatus };

export interface UniversityResponsible {
  id: string;
  name: string;
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
  healthScore: number;
  lastInteractionAt: string;
  attention: boolean;
  /** Mock relationship ids mirror the fields expected from the future analytics API. */
  programIds?: string[];
  productIds?: string[];
}

export type UniversitySortColumn = 'name' | 'responsible' | 'programs' | 'stage' | 'health_score' | 'last_interaction';
export type SortOrder = 'asc' | 'desc';

export interface UniversityFilters {
  search: string;
  city: string;
  universityIds: string[];
  programIds: string[];
  productIds: string[];
  responsibleIds: string[];
  healthStatuses: HealthStatus[];
  workflowStageId: string;
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

const programCounts = (planned: number, active: number, launched = 0, archived = 0): ProgramStatusCounts => ({
  planned,
  active,
  launched,
  archived,
});

const responsible = {
  anna: { id: 'responsible-anna', name: 'Анна Иванова' },
  boris: { id: 'responsible-boris', name: 'Борис Петров' },
  elena: { id: 'responsible-elena', name: 'Елена Смирнова' },
  dmitry: { id: 'responsible-dmitry', name: 'Дмитрий Волков' },
} satisfies Record<string, UniversityResponsible>;

const stage = {
  preparation: { id: 'preparation', name: 'Подготовка', tone: 'neutral' },
  launch: { id: 'launch', name: 'Запуск программы', tone: 'brand' },
  support: { id: 'support', name: 'Сопровождение', tone: 'warning' },
  completed: { id: 'completed', name: 'Завершён', tone: 'success' },
} satisfies Record<string, UniversityStage>;

const universitiesMock: UniversityListItem[] = [
  { id: 'university-001', name: 'Московский технический университет связи и информатики', city: 'Москва', responsible: responsible.anna, programsCount: 12, programStatusCounts: programCounts(2, 5, 4, 1), currentStage: stage.support, healthScore: 42, lastInteractionAt: '2026-09-19T10:30:00+03:00', attention: true },
  { id: 'university-002', name: 'Санкт-Петербургский политехнический университет', city: 'Санкт-Петербург', responsible: responsible.boris, programsCount: 8, programStatusCounts: programCounts(1, 4, 3), currentStage: stage.launch, healthScore: 67, lastInteractionAt: '2026-09-17T14:00:00+03:00', attention: true },
  { id: 'university-003', name: 'Уральский федеральный университет', city: 'Екатеринбург', responsible: responsible.elena, programsCount: 6, programStatusCounts: programCounts(2, 2, 2), currentStage: stage.preparation, healthScore: 58, lastInteractionAt: '2026-09-13T09:15:00+03:00', attention: true },
  { id: 'university-004', name: 'Казанский федеральный университет', city: 'Казань', responsible: responsible.dmitry, programsCount: 10, programStatusCounts: programCounts(1, 5, 4), currentStage: stage.support, healthScore: 73, lastInteractionAt: '2026-09-18T16:45:00+03:00', attention: true },
  { id: 'university-005', name: 'Новосибирский государственный университет', city: 'Новосибирск', responsible: responsible.anna, programsCount: 5, programStatusCounts: programCounts(1, 2, 2), currentStage: stage.preparation, healthScore: 88, lastInteractionAt: '2026-09-20T11:10:00+03:00', attention: true },
  { id: 'university-006', name: 'Дальневосточный федеральный университет', city: 'Владивосток', responsible: responsible.boris, programsCount: 7, programStatusCounts: programCounts(2, 3, 2), currentStage: stage.launch, healthScore: 91, lastInteractionAt: '2026-09-16T13:20:00+03:00', attention: false },
  { id: 'university-007', name: 'Южный федеральный университет', city: 'Ростов-на-Дону', responsible: responsible.elena, programsCount: 4, programStatusCounts: programCounts(1, 1, 2), currentStage: stage.completed, healthScore: 96, lastInteractionAt: '2026-09-12T15:30:00+03:00', attention: false },
  { id: 'university-008', name: 'Самарский университет имени академика Королёва', city: 'Самара', responsible: null, programsCount: 3, programStatusCounts: programCounts(1, 2), currentStage: stage.preparation, healthScore: 61, lastInteractionAt: '2026-09-10T08:40:00+03:00', attention: false },
  { id: 'university-009', name: 'Национальный исследовательский ядерный университет МИФИ', city: 'Москва', responsible: responsible.dmitry, programsCount: 11, programStatusCounts: programCounts(1, 5, 5), currentStage: stage.support, healthScore: 84, lastInteractionAt: '2026-09-15T12:00:00+03:00', attention: false },
  { id: 'university-010', name: 'Томский государственный университет', city: 'Томск', responsible: responsible.anna, programsCount: 9, programStatusCounts: programCounts(2, 3, 4), currentStage: stage.launch, healthScore: 79, lastInteractionAt: '2026-09-14T17:25:00+03:00', attention: false },
  { id: 'university-011', name: 'Нижегородский государственный университет имени Лобачевского', city: 'Нижний Новгород', responsible: responsible.boris, programsCount: 2, programStatusCounts: programCounts(1, 1), currentStage: stage.preparation, healthScore: 52, lastInteractionAt: '2026-09-08T10:05:00+03:00', attention: true },
  { id: 'university-012', name: 'Воронежский государственный университет', city: 'Воронеж', responsible: responsible.elena, programsCount: 6, programStatusCounts: programCounts(1, 3, 2), currentStage: stage.completed, healthScore: 89, lastInteractionAt: '2026-09-19T09:45:00+03:00', attention: false },
  { id: 'university-013', name: 'Пермский национальный исследовательский политехнический университет', city: 'Пермь', responsible: responsible.dmitry, programsCount: 5, programStatusCounts: programCounts(2, 2, 1), currentStage: stage.support, healthScore: 64, lastInteractionAt: '2026-09-06T14:35:00+03:00', attention: false },
  { id: 'university-014', name: 'Балтийский федеральный университет имени Иммануила Канта', city: 'Калининград', responsible: null, programsCount: 3, programStatusCounts: programCounts(1, 1, 1), currentStage: stage.launch, healthScore: 76, lastInteractionAt: '2026-09-11T16:10:00+03:00', attention: false },
  { id: 'university-015', name: 'Сибирский федеральный университет', city: 'Красноярск', responsible: responsible.anna, programsCount: 8, programStatusCounts: programCounts(1, 4, 3), currentStage: stage.support, healthScore: 86, lastInteractionAt: '2026-09-18T09:00:00+03:00', attention: false },
  { id: 'university-016', name: 'Московский государственный технический университет имени Баумана', city: 'Москва', responsible: responsible.boris, programsCount: 13, programStatusCounts: programCounts(2, 6, 5), currentStage: stage.completed, healthScore: 98, lastInteractionAt: '2026-09-20T13:50:00+03:00', attention: false },
  { id: 'university-017', name: 'Омский государственный технический университет', city: 'Омск', responsible: responsible.elena, programsCount: 4, programStatusCounts: programCounts(1, 2, 1), currentStage: stage.preparation, healthScore: 35, lastInteractionAt: '2026-09-05T11:30:00+03:00', attention: true },
  { id: 'university-018', name: 'Саратовский государственный университет', city: 'Саратов', responsible: responsible.dmitry, programsCount: 7, programStatusCounts: programCounts(1, 3, 3), currentStage: stage.launch, healthScore: 82, lastInteractionAt: '2026-09-16T10:20:00+03:00', attention: false },
];

export const universitiesQueryKey = ['universities'] as const;

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

function compareValues(left: string | number, right: string | number): number {
  if (typeof left === 'number' && typeof right === 'number') return left - right;
  return String(left).localeCompare(String(right), 'ru', { sensitivity: 'base' });
}

export async function getUniversities(params: UniversityListQuery): Promise<PaginatedResult<UniversityListItem>> {
  const { filters } = params;
  const search = filters.search.trim().toLocaleLowerCase('ru-RU');
  let filtered = universitiesWithRelationships.filter((item) => {
    if (search && !item.name.toLocaleLowerCase('ru-RU').includes(search)) return false;
    if (filters.city && item.city !== filters.city) return false;
    if (filters.universityIds.length && !filters.universityIds.includes(item.id)) return false;
    if (filters.programIds.length && !filters.programIds.some((id) => item.programIds?.includes(id))) return false;
    if (filters.productIds.length && !filters.productIds.some((id) => item.productIds?.includes(id))) return false;
    if (filters.responsibleIds.length && (!item.responsible || !filters.responsibleIds.includes(item.responsible.id))) return false;
    if (filters.workflowStageId && item.currentStage.id !== filters.workflowStageId) return false;
    if (filters.healthStatuses.length && !filters.healthStatuses.includes(getHealthStatus(item.healthScore))) return false;
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
            : params.sort === 'health_score' ? left.healthScore
              : params.sort === 'last_interaction' ? left.lastInteractionAt
                : left.name;
      const rightValue = params.sort === 'responsible' ? right.responsible?.name ?? ''
        : params.sort === 'programs' ? right.programsCount
          : params.sort === 'stage' ? right.currentStage.name
            : params.sort === 'health_score' ? right.healthScore
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

export type UniversityPassportEventType = 'meeting' | 'document' | 'workflow' | 'note';

export interface UniversityPassportMetrics {
  activePrograms: number;
  teachers: { total: number; ready: number; attention: number };
  licenses: { active: number; expiring: number; overdue: number };
  documents: { total: number; signed: number; overdue: number };
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
  healthScore: number;
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
export async function getUniversityPassport(id: string): Promise<UniversityPassport> {
  const university = universitiesWithRelationships.find((item) => item.id === id);
  if (!university) throw new Error('Университет не найден');

  const launchedPrograms = university.programStatusCounts.launched ?? 0;
  const activePrograms = launchedPrograms + (university.programStatusCounts.active ?? 0);
  const numericId = Number(id.split('-').at(-1)) || 1;
  const teachersTotal = 42 + numericId;
  const teachersAttention = university.attention ? 8 : 3;
  const workflowStatus: UniversityPassportWorkflow['status'] = university.currentStage.id === stage.completed.id
    ? 'completed'
    : university.attention ? 'attention' : 'in_progress';

  return {
    id: university.id,
    name: university.name,
    city: university.city,
    healthScore: university.healthScore,
    metrics: {
      activePrograms,
      teachers: { total: teachersTotal, ready: teachersTotal - teachersAttention, attention: teachersAttention },
      licenses: { active: 4 + (numericId % 3), expiring: university.attention ? 2 : 1, overdue: university.attention ? 1 : 0 },
      documents: { total: 24 + numericId, signed: 19 + (numericId % 4), overdue: university.attention ? 2 : 0 },
    },
    workflow: {
      currentStage: university.currentStage,
      status: workflowStatus,
      deadline: university.attention ? '2026-09-18' : '2026-10-08',
      overdue: university.attention && university.currentStage.id !== stage.completed.id,
      responsible: university.responsible,
      completedSteps: university.currentStage.id === stage.completed.id ? 6 : Math.max(1, workflowOrder.findIndex((item) => item.id === university.currentStage.id) + 2),
      totalSteps: 6,
      nextStage: getPassportNextStage(university.currentStage.id),
    },
    timeline: [
      { id: `${id}-event-1`, type: 'meeting', occurredAt: '2026-09-20T11:30:00+03:00', description: 'Провели встречу с координатором программы.' },
      { id: `${id}-event-2`, type: 'document', occurredAt: '2026-09-18T16:10:00+03:00', description: 'Получили подписанный пакет документов.' },
      { id: `${id}-event-3`, type: 'workflow', occurredAt: '2026-09-16T13:45:00+03:00', description: `Этап изменён: ${university.currentStage.name}.` },
      { id: `${id}-event-4`, type: 'note', occurredAt: '2026-09-14T09:20:00+03:00', description: 'Добавили заметку по подготовке преподавателей.' },
      { id: `${id}-event-5`, type: 'meeting', occurredAt: '2026-09-12T15:00:00+03:00', description: 'Согласовали план ближайших запусков.' },
    ],
  };
}

export type UniversityWorkflowStageStatus = 'completed' | 'current' | 'pending' | 'skipped' | 'overdue';

export interface UniversityWorkflowComment {
  id: string;
  author: string;
  occurredAt: string;
  text: string;
}

export interface UniversityWorkflowAttachment {
  id: string;
  fileName: string;
  fileType: string;
  fileSize: string;
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
}

export interface UniversityWorkflowStage {
  id: string;
  orderIndex: number;
  name: string;
  status: UniversityWorkflowStageStatus;
  deadline: string;
  responsible: UniversityResponsible | null;
  comments: UniversityWorkflowComment[];
  attachments: UniversityWorkflowAttachment[];
  tasks: UniversityWorkflowTask[];
  transitions: UniversityWorkflowTransition[];
}

export interface UniversityWorkflow {
  universityId: string;
  stages: UniversityWorkflowStage[];
}

export const universityWorkflowQueryKey = (id: string) => ['university-workflow', id] as const;

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
  if (index === currentIndex && currentIndex < workflowStageNames.length - 1) return 'current';
  if (index < currentIndex) return index === 2 && numericId % 2 === 0 ? 'skipped' : 'completed';
  if (index === currentIndex + 1 && attention) return 'overdue';
  return 'pending';
}

function getWorkflowDeadline(index: number, status: UniversityWorkflowStageStatus): string {
  if (status === 'overdue') return '2026-09-18';
  if (status === 'current') return '2026-09-30';
  return `2026-${String(Math.min(12, 3 + Math.floor(index / 2))).padStart(2, '0')}-${String(8 + (index % 6)).padStart(2, '0')}`;
}

function getWorkflowComments(id: string, index: number, responsible: UniversityResponsible | null): UniversityWorkflowComment[] {
  const author = responsible?.name ?? 'Анна Иванова';
  return [
    { id: `${id}-stage-${index + 1}-comment-1`, author, occurredAt: '2026-09-20T11:30:00+03:00', text: index === 10 ? 'Зафиксировали контрольные точки запуска и ответственных.' : 'Обновили материалы этапа и подтвердили следующий шаг.' },
    { id: `${id}-stage-${index + 1}-comment-2`, author: 'Борис Петров', occurredAt: '2026-09-18T16:10:00+03:00', text: 'Проверили комплект данных со стороны вуза.' },
    { id: `${id}-stage-${index + 1}-comment-3`, author: 'Елена Смирнова', occurredAt: '2026-09-16T13:45:00+03:00', text: 'Добавили комментарий методиста к этапу.' },
    { id: `${id}-stage-${index + 1}-comment-4`, author: 'Анна Иванова', occurredAt: '2026-09-12T15:00:00+03:00', text: 'Согласовали план ближайших запусков.' },
  ];
}

/** Typed frontend adapter for the future GET /universities/{id}/workflow endpoint. */
export async function getUniversityWorkflow(id: string): Promise<UniversityWorkflow> {
  const university = getUniversityOrThrow(id);
  const numericId = getUniversityNumericId(id);
  const currentIndex = workflowStageIndex[university.currentStage.id] ?? 3;
  const stages = workflowStageNames.map((name, index) => {
    const status = getWorkflowStageStatus(index, currentIndex, university.attention, numericId);
    const previousStatus = index === 0 ? 'pending' : getWorkflowStageStatus(index - 1, currentIndex, university.attention, numericId);
    const attachments: UniversityWorkflowAttachment[] = index % 3 === 0
      ? [{ id: `${id}-stage-${index + 1}-attachment`, fileName: index === 6 ? 'дорожная-карта-запуска.pdf' : 'материалы-этапа.docx', fileType: index === 6 ? 'PDF' : 'DOCX', fileSize: index === 6 ? '1,8 МБ' : '420 КБ' }]
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
      responsible: university.responsible,
      comments: getWorkflowComments(id, index, university.responsible),
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

  return { universityId: university.id, stages };
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

export const universityHistoryQueryKey = (id: string, filters: UniversityHistoryFilters) => ['university-history', id, filters] as const;

const historyEvents = (id: string, university: UniversityListItem): UniversityHistoryEvent[] => {
  const anna = responsible.anna;
  const boris = responsible.boris;
  const currentStageName = university.currentStage.name;
  return [
    { id: `${id}-history-1`, occurredAt: '2026-09-20T11:30:00+03:00', type: 'meeting', user: anna, action: 'Проведена встреча', details: 'Рабочая встреча с координатором программы', entity: { id: `${id}-meeting-1`, label: 'Встреча с координатором' } },
    { id: `${id}-history-2`, occurredAt: '2026-09-19T15:20:00+03:00', type: 'audit', user: boris, action: 'Изменён срок этапа', details: `${currentStageName} → новый срок 30 сент. 2026 г.`, entity: { id: `${id}-workflow-stage-11`, label: currentStageName }, oldValues: { deadline: '2026-09-18', status: 'attention' }, newValues: { deadline: '2026-09-30', status: 'current' }, ip: '10.24.18.42', userAgent: 'Chrome 128 · macOS' },
    { id: `${id}-history-3`, occurredAt: '2026-09-18T16:10:00+03:00', type: 'document', user: boris, action: 'Подписан документ', details: 'Договор на обучение · contract-2026.pdf', entity: { id: `${id}-document-1`, label: 'Договор на обучение' } },
    { id: `${id}-history-4`, occurredAt: '2026-09-17T10:05:00+03:00', type: 'workflow', user: anna, action: 'Этап завершён', details: 'Подготовка преподавателей → Подготовка инфраструктуры', entity: { id: `${id}-workflow-stage-7`, label: 'Подготовка инфраструктуры' } },
    { id: `${id}-history-5`, occurredAt: '2026-09-16T13:45:00+03:00', type: 'note', user: { id: 'responsible-elena', name: 'Елена Смирнова' }, action: 'Добавлена заметка', details: 'Нужно подтвердить готовность аудитории к пилоту.', entity: { id: `${id}-note-1`, label: 'Подготовка к пилоту' } },
    { id: `${id}-history-6`, occurredAt: '2026-09-15T09:30:00+03:00', type: 'audit', user: anna, action: 'Изменён ответственный', details: 'Ответственный обновлён в карточке Workflow', entity: { id: `${id}-workflow-stage-10`, label: 'Пилотный запуск' }, oldValues: { responsible: 'Борис Петров' }, newValues: { responsible: anna.name }, ip: '10.24.18.42', userAgent: 'Chrome 128 · macOS' },
    { id: `${id}-history-7`, occurredAt: '2026-09-12T15:00:00+03:00', type: 'meeting', user: { id: 'responsible-elena', name: 'Елена Смирнова' }, action: 'Зафиксированы договорённости', details: 'Согласовали план ближайших запусков', entity: { id: `${id}-meeting-2`, label: 'План ближайших запусков' } },
    { id: `${id}-history-8`, occurredAt: '2026-09-11T12:20:00+03:00', type: 'document', user: anna, action: 'Загружен документ', details: 'Приложение к договору · appendix-programs.docx', entity: { id: `${id}-document-2`, label: 'Приложение к договору' } },
    { id: `${id}-history-9`, occurredAt: '2026-09-09T17:10:00+03:00', type: 'workflow', user: boris, action: 'Этап изменён', details: `Текущий этап: ${currentStageName}`, entity: { id: `${id}-workflow-stage-11`, label: currentStageName } },
    { id: `${id}-history-10`, occurredAt: '2026-09-06T14:35:00+03:00', type: 'note', user: anna, action: 'Добавлена заметка', details: 'Обновили план подготовки преподавателей.', entity: { id: `${id}-note-2`, label: 'План подготовки преподавателей' } },
  ];
};

export function getUniversityHistoryFilterOptions(id: string): UniversityHistoryFilterOptions {
  const university = getUniversityOrThrow(id);
  const events = historyEvents(id, university);
  return {
    users: [...new Map(events.map((event) => [event.user.id, event.user])).values()].sort((left, right) => left.name.localeCompare(right.name, 'ru')),
    entities: [...new Map(events.map((event) => [event.entity.id, event.entity])).values()].sort((left, right) => left.label.localeCompare(right.label, 'ru')),
  };
}

/** Typed frontend adapter for the future GET /universities/{id}/history endpoint. */
export async function getUniversityHistory(id: string, filters: UniversityHistoryFilters): Promise<UniversityHistoryEvent[]> {
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

export type HealthScoreReasonSeverity = 'high' | 'medium' | 'low';

export interface UniversityHealthScoreBreakdown {
  id: 'tasks' | 'documents' | 'stages' | 'teachers' | 'launch';
  label: string;
  weight: number;
  score: number;
  inputCounters: Array<{ label: string; value: number }>;
}

export interface UniversityHealthScoreReason {
  id: string;
  severity: HealthScoreReasonSeverity;
  title: string;
  description: string;
  details?: string;
  inputCounters?: Array<{ label: string; value: number }>;
}

export interface UniversityHealthScoreHistoryPoint {
  date: string;
  score: number;
}

export interface UniversityHealthScore {
  universityId: string;
  currentScore: number;
  status: HealthStatus;
  breakdown: UniversityHealthScoreBreakdown[];
  reasons: UniversityHealthScoreReason[];
  history: UniversityHealthScoreHistoryPoint[];
  previousSnapshot: UniversityHealthScoreHistoryPoint;
}

export const universityHealthScoreQueryKey = (id: string) => ['university-health-score', id] as const;

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function createHealthHistory(currentScore: number, numericId: number): UniversityHealthScoreHistoryPoint[] {
  const today = new Date(Date.UTC(2026, 8, 22));
  return Array.from({ length: 30 }, (_, index) => {
    const date = new Date(today);
    date.setUTCDate(today.getUTCDate() - (29 - index));
    const trend = (index - 22) * (numericId % 3 === 0 ? 0.28 : 0.16);
    const wave = ((index * 7 + numericId) % 5) - 2;
    return { date: date.toISOString().slice(0, 10), score: clampScore(currentScore - 3 + trend + wave) };
  }).map((point, index, points) => index === points.length - 1 ? { ...point, score: currentScore } : point);
}

/** Temporary typed adapter for the future GET /universities/{id}/health-score endpoints. */
export async function getUniversityHealthScore(id: string): Promise<UniversityHealthScore> {
  const university = universitiesWithRelationships.find((item) => item.id === id);
  if (!university) throw new Error('Университет не найден');

  const numericId = Number(id.split('-').at(-1)) || 1;
  const currentScore = university.healthScore;
  const taskScore = clampScore(currentScore + (university.attention ? -9 : 4));
  const documentScore = clampScore(currentScore + (numericId % 2 === 0 ? 3 : -4));
  const stageScore = clampScore(currentScore + (university.currentStage.id === stage.completed.id ? 8 : -3));
  const teacherScore = clampScore(currentScore + (numericId % 3 === 0 ? -7 : 2));
  const launchScore = clampScore(currentScore + (university.programStatusCounts.launched ? 3 : -6));
  const history = createHealthHistory(currentScore, numericId);
  const previousSnapshot = history[history.length - 8] ?? history[0];
  const reasons: UniversityHealthScoreReason[] = university.attention
    ? [
      { id: `${id}-reason-tasks`, severity: 'high', title: 'Есть просроченные задачи', description: 'Часть контрольных задач не закрыта в установленный срок.', details: 'Проверьте задачи workflow и назначьте ответственных.', inputCounters: [{ label: 'Всего задач', value: 18 }, { label: 'Просрочено', value: 4 }] },
      { id: `${id}-reason-documents`, severity: 'medium', title: 'Не все документы подписаны', description: 'Для запуска следующего этапа не хватает подтверждённых документов.', details: 'Нужно проверить пакет документов по двум активным программам.', inputCounters: [{ label: 'Документов', value: 24 }, { label: 'Ожидают подписи', value: 3 }] },
      { id: `${id}-reason-teachers`, severity: 'low', title: 'Преподавателям требуется обновление данных', description: 'У нескольких преподавателей не подтверждена готовность к запуску.', inputCounters: [{ label: 'Требуют внимания', value: 8 }] },
    ]
    : [
      { id: `${id}-reason-stable`, severity: 'low', title: 'Критичных факторов не обнаружено', description: 'Основные показатели вуза находятся в стабильном диапазоне.', details: 'Текущие задачи, документы и этапы обновляются без критичных отклонений.' },
    ];

  return {
    universityId: university.id,
    currentScore,
    status: getHealthStatus(currentScore),
    breakdown: [
      { id: 'tasks', label: 'Задачи', weight: 25, score: taskScore, inputCounters: [{ label: 'Всего задач', value: 18 }, { label: 'Выполнено', value: 14 }, { label: 'Просрочено', value: university.attention ? 4 : 1 }] },
      { id: 'documents', label: 'Документы', weight: 20, score: documentScore, inputCounters: [{ label: 'Всего документов', value: 24 }, { label: 'Подписано', value: university.attention ? 19 : 23 }, { label: 'Просрочено', value: university.attention ? 2 : 0 }] },
      { id: 'stages', label: 'Этапы', weight: 20, score: stageScore, inputCounters: [{ label: 'Всего этапов', value: 6 }, { label: 'Завершено', value: university.currentStage.id === stage.completed.id ? 6 : 3 }, { label: 'Текущий этап', value: 1 }] },
      { id: 'teachers', label: 'Преподаватели', weight: 20, score: teacherScore, inputCounters: [{ label: 'Всего преподавателей', value: 42 + numericId }, { label: 'Готовы', value: university.attention ? 35 + numericId : 39 + numericId }, { label: 'Требуют внимания', value: university.attention ? 8 : 3 }] },
      { id: 'launch', label: 'Запуск', weight: 15, score: launchScore, inputCounters: [{ label: 'Активных программ', value: (university.programStatusCounts.active ?? 0) + (university.programStatusCounts.launched ?? 0) }, { label: 'Запущено', value: university.programStatusCounts.launched ?? 0 }] },
    ],
    reasons,
    history,
    previousSnapshot,
  };
}

export interface UniversityProgramRow {
  id: string;
  direction: string;
  name: string;
  status: ProgramStatus;
  launchDate: string;
  responsible: UniversityResponsible | null;
  teachersCount: number;
  studentsCount: number;
}

export type TeacherReadiness = 'ready' | 'attention' | 'expired';

export interface UniversityTeacherRow {
  id: string;
  name: string;
  position: string;
  readiness: TeacherReadiness;
  nextTrainingDate: string;
  allowedPrograms: string[];
}

export interface TeacherQualification {
  id: string;
  name: string;
  obtainedAt: string;
  expiresAt: string;
  status: ExpirationStatus;
  document: { name: string; fileType: string; fileSize: string; downloadUrl: string | null } | null;
}

export interface TeacherTraining {
  id: string;
  name: string;
  provider: string;
  completedAt: string;
  hours: number;
  certificate: string | null;
}

export type TeacherCertificateStatus = ExpirationStatus;

export interface TeacherCertificate {
  id: string;
  name: string;
  issuer: string;
  issuedAt: string;
  expiresAt: string;
  mandatory: boolean;
  program: string;
  status: TeacherCertificateStatus;
  document: { name: string; fileType: string; fileSize: string; downloadUrl: string | null } | null;
}

export interface TeacherPassportProfile extends UniversityTeacherRow {
  universityId: string;
  universityName: string;
  universityCity: string;
  readinessReason: string;
}

export interface TeacherPassport {
  teacher: TeacherPassportProfile;
  qualifications: TeacherQualification[];
  trainings: TeacherTraining[];
  certificates: TeacherCertificate[];
  allowedPrograms: Array<{ id: string; name: string }>;
}

export interface UniversityStudentsByProgram {
  programId: string;
  programName: string;
  active: number;
  graduated: number;
  total: number;
}

export interface UniversityStudentsSummary {
  total: number;
  active: number;
  graduated: number;
  academicLeave: number;
  byProgram: UniversityStudentsByProgram[];
}

export type UniversityProductStatus = 'active' | 'expiring' | 'expired';

export interface UniversityProductRow {
  id: string;
  name: string;
  version: string;
  vendor: string;
  status: UniversityProductStatus;
  licenseNumber: string;
  expiresAt: string;
}

export const universityProgramsQueryKey = (id: string) => ['university-programs', id] as const;
export const universityTeachersQueryKey = (id: string) => ['university-teachers', id] as const;
export const teacherPassportQueryKey = (id: string) => ['teacher-passport', id] as const;
export const universityStudentsQueryKey = (id: string) => ['university-students', id] as const;
export const universityProductsQueryKey = (id: string) => ['university-products', id] as const;

const programDirections = ['Аналитика и данные', 'Цифровая трансформация', 'Информационная безопасность', 'Управление проектами'];
const programNames = ['Аналитика данных', 'Цифровая экономика', 'Кибербезопасность', 'ИТ-менеджмент'];
const teacherNames = ['Мария Кузнецова', 'Алексей Орлов', 'Ольга Соколова', 'Илья Морозов', 'Наталья Лебедева', 'Сергей Фёдоров'];
const teacherPositions = ['Руководитель программы', 'Старший преподаватель', 'Преподаватель-практик'];

function getUniversityNumericId(id: string): number {
  return Number(id.split('-').at(-1)) || 1;
}

function getUniversityOrThrow(id: string): UniversityListItem {
  const university = universitiesWithRelationships.find((item) => item.id === id);
  if (!university) throw new Error('Университет не найден');
  return university;
}

/** Typed frontend adapter for the future university programs endpoint. */
export async function getUniversityPrograms(id: string): Promise<UniversityProgramRow[]> {
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
    teachersCount: 8 + ((index + numericId) % 7),
    studentsCount: 48 + ((index * 17 + numericId * 5) % 120),
  }));
}

/** Typed frontend adapter for the future university teachers endpoint. */
export async function getUniversityTeachers(id: string): Promise<UniversityTeacherRow[]> {
  getUniversityOrThrow(id);
  return universityTeachersFixture(id);
}

function getTeacherPassportContext(id: string): { teacher: UniversityTeacherRow; university: UniversityListItem } {
  const parts = id.split('-');
  const universityId = `university-${String(Number(parts[1]) || 1).padStart(3, '0')}`;
  const university = getUniversityOrThrow(universityId);
  const teacherIndex = Math.max(0, (Number(parts[2]) || 1) - 1);
  const teachers = universityTeachersFixture(universityId);
  return { university, teacher: teachers[teacherIndex] ?? teachers[0] };
}

function universityTeachersFixture(id: string): UniversityTeacherRow[] {
  const numericId = getUniversityNumericId(id);
  const readiness: TeacherReadiness[] = ['ready', 'attention', 'expired', 'ready', 'ready', 'attention'];
  const count = 5 + (numericId % 2);
  return Array.from({ length: count }, (_, index) => ({
    id: `teacher-${String(numericId).padStart(3, '0')}-${index + 1}`,
    name: teacherNames[(index + numericId) % teacherNames.length],
    position: teacherPositions[(index + numericId) % teacherPositions.length],
    readiness: readiness[(index + numericId) % readiness.length],
    nextTrainingDate: `2026-${String(((index + numericId) % 9) + 1).padStart(2, '0')}-${String(((index * 4 + numericId) % 22) + 3).padStart(2, '0')}`,
    allowedPrograms: [
      programNames[(index + numericId) % programNames.length],
      ...(index % 2 === 0 ? [programNames[(index + numericId + 1) % programNames.length]] : []),
    ],
  }));
}

const qualificationNames = ['Педагогический дизайн', 'Информационная безопасность', 'Управление образовательными проектами'];
const certificateNames = ['Информационная безопасность', 'Цифровая педагогика', 'Управление проектами', 'Основы аналитики данных'];

function getReadinessReason(readiness: TeacherReadiness, certificates: TeacherCertificate[]): string {
  const expiring = certificates.find((item) => item.mandatory && item.status === 'expires_soon');
  const expired = certificates.find((item) => item.mandatory && item.status === 'expired');
  if (readiness === 'ready') return 'Все обязательные сертификаты актуальны';
  if (readiness === 'expired' && expired) return `Истёк обязательный сертификат: ${expired.name}`;
  if (expiring) return `Сертификат «${expiring.name}» истекает ${new Intl.DateTimeFormat('ru-RU').format(new Date(expiring.expiresAt))}`;
  return 'Нужно обновить данные о квалификации';
}

/** Typed frontend adapter for the future GET /teachers/{id}/passport endpoint. */
export async function getTeacherPassport(id: string): Promise<TeacherPassport> {
  const { teacher, university } = getTeacherPassportContext(id);
  const numericId = getUniversityNumericId(university.id);
  const certificateDates = teacher.readiness === 'expired'
    ? ['2026-08-15', '2027-02-20', '2026-09-10', '2027-03-05']
    : teacher.readiness === 'attention'
      ? ['2026-10-15', '2027-02-20', '2027-04-10', '2027-03-05']
      : ['2027-01-15', '2027-02-20', '2027-04-10', '2027-03-05'];
  const certificates: TeacherCertificate[] = certificateNames.map((name, index) => {
    const expiresAt = certificateDates[index];
    return {
      id: `${id}-certificate-${index + 1}`,
      name,
      issuer: ['Ростелеком', 'ИТ-Академия', 'НОЦ «Цифровые кадры»', 'Университетская школа'][index],
      issuedAt: `202${index % 2 + 3}-${String(((numericId + index) % 8) + 1).padStart(2, '0')}-12`,
      expiresAt,
      mandatory: index < 3,
      program: programNames[(index + numericId) % programNames.length],
      status: getExpirationStatus(expiresAt),
      document: {
        name: `${name}.pdf`,
        fileType: 'PDF',
        fileSize: `${1 + index}.2 МБ`,
        downloadUrl: null,
      },
    };
  }).sort((left, right) => Number(right.mandatory) - Number(left.mandatory) || left.expiresAt.localeCompare(right.expiresAt));

  const qualifications: TeacherQualification[] = qualificationNames.map((name, index) => {
    const expiresAt = [`2027-04-18`, `2026-12-12`, `2026-09-10`][index];
    return {
      id: `${id}-qualification-${index + 1}`,
      name,
      obtainedAt: `202${index + 2}-0${index + 3}-18`,
      expiresAt,
      status: getExpirationStatus(expiresAt),
      document: index === 2 ? null : { name: `${name}.pdf`, fileType: 'PDF', fileSize: `${2 + index}.4 МБ`, downloadUrl: null },
    };
  }).sort((left, right) => right.obtainedAt.localeCompare(left.obtainedAt));

  const trainings: TeacherTraining[] = [
    { id: `${id}-training-1`, name: 'Современные методы онлайн-обучения', provider: 'Ростелеком Лицей', completedAt: '2026-06-24', hours: 24, certificate: 'Сертификат RTK-2026-184' },
    { id: `${id}-training-2`, name: 'Практики безопасной разработки', provider: 'ИТ-Академия', completedAt: '2025-11-18', hours: 16, certificate: 'Сертификат IT-2025-071' },
    { id: `${id}-training-3`, name: 'Работа с данными в образовательных программах', provider: 'НОЦ «Цифровые кадры»', completedAt: '2025-04-09', hours: 32, certificate: null },
  ];

  return {
    teacher: {
      ...teacher,
      universityId: university.id,
      universityName: university.name,
      universityCity: university.city,
      readinessReason: getReadinessReason(teacher.readiness, certificates),
    },
    qualifications,
    trainings,
    certificates,
    allowedPrograms: teacher.allowedPrograms.map((name, index) => ({ id: `${university.id}-program-${index + 1}`, name })),
  };
}

/** Typed frontend adapter for the future aggregate students endpoint. */
export async function getUniversityStudentsSummary(id: string): Promise<UniversityStudentsSummary> {
  const university = getUniversityOrThrow(id);
  const numericId = getUniversityNumericId(id);
  const byProgram = programNames.map((programName, index) => {
    const total = 42 + ((numericId * 9 + index * 13) % 65);
    const graduated = 8 + ((numericId + index * 4) % 18);
    const active = Math.max(0, total - graduated - ((numericId + index) % 5));
    return { programId: `${id}-program-${index + 1}`, programName, active, graduated, total };
  });
  const total = byProgram.reduce((sum, item) => sum + item.total, 0);
  const graduated = byProgram.reduce((sum, item) => sum + item.graduated, 0);
  const academicLeave = 2 + (numericId % 5);

  return {
    total,
    active: Math.max(0, total - graduated - academicLeave),
    graduated,
    academicLeave,
    byProgram: university.programsCount ? byProgram : [],
  };
}

/** Typed frontend adapter for the future university products/licenses endpoint. */
export async function getUniversityProducts(id: string): Promise<UniversityProductRow[]> {
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

export type UniversityDocumentStatus = 'signed' | 'pending' | 'expired';

export interface UniversityDocumentRow {
  id: string;
  type: string;
  name: string;
  fileName: string;
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
  occurredAt: string;
  type: UniversityMeetingType;
  subject: string;
  participants: UniversityMeetingParticipant[];
  outcome: string;
  nextAction: string;
  dueDate: string | null;
  author: string;
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

export const universityLicensesQueryKey = (id: string) => ['university-licenses', id] as const;
export const universityDocumentsQueryKey = (id: string) => ['university-documents', id] as const;
export const universityMeetingsQueryKey = (id: string) => ['university-meetings', id] as const;
export const universityResponsiblesQueryKey = (id: string) => ['university-responsibles', id] as const;

/** Typed frontend adapter for the future university licenses endpoint. */
export async function getUniversityLicenses(id: string): Promise<UniversityLicenseRow[]> {
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

/** Typed frontend adapter for the future university documents endpoint. */
export async function getUniversityDocuments(id: string): Promise<UniversityDocumentRow[]> {
  const university = getUniversityOrThrow(id);
  const numericId = getUniversityNumericId(id);
  const documents = [
    ['Договор', 'Договор на обучение', 'contract-2026.pdf', '2,4 МБ', 'signed'],
    ['Приложение', 'Приложение к договору', 'appendix-programs.docx', '184 КБ', 'pending'],
    ['Акт', 'Акт оказанных услуг', 'service-act-08.pdf', '1,1 МБ', 'signed'],
    ['Лицензия', 'Лицензия на образовательную деятельность', 'education-license.pdf', '856 КБ', 'expired'],
    ['Отчёт', 'Отчёт о запуске программы', 'launch-report.xlsx', '326 КБ', 'signed'],
  ] as const;
  return documents.map(([type, name, fileName, fileSize, status], index) => ({
    id: `${id}-document-${index + 1}`,
    type,
    name,
    fileName,
    fileSize,
    signedAt: status === 'signed' ? `2026-0${((index + numericId) % 8) + 1}-12` : null,
    expiresAt: index === 3 ? '2026-08-15' : index === 1 ? '2026-11-30' : null,
    status,
    uploadedBy: index % 2 === 0 ? university.responsible?.name ?? 'Анна Иванова' : 'Борис Петров',
    uploadedAt: `2026-0${((index + numericId) % 8) + 1}-${String(index + 10).padStart(2, '0')}`,
    downloadUrl: undefined,
  }));
}

/** Typed frontend adapter for the future university meetings endpoint. */
export async function getUniversityMeetings(id: string): Promise<UniversityMeetingRow[]> {
  const university = getUniversityOrThrow(id);
  const numericId = getUniversityNumericId(id);
  const types: UniversityMeetingType[] = ['online', 'offline', 'phone', 'email', 'online'];
  const subjects = ['Согласование плана запуска', 'Рабочая встреча с координатором', 'Уточнение пакета документов', 'Подтверждение сроков обучения', 'Итоги месяца'];
  const participants: UniversityMeetingParticipant[] = [
    { id: 'participant-anna', name: 'Анна Иванова', initials: 'АИ' },
    { id: 'participant-boris', name: 'Борис Петров', initials: 'БП' },
    { id: 'participant-elena', name: 'Елена Смирнова', initials: 'ЕС' },
  ];
  return subjects.map((subject, index) => ({
    id: `${id}-meeting-${index + 1}`,
    occurredAt: `2026-09-${String(20 - index * 3).padStart(2, '0')}T${String(10 + index).padStart(2, '0')}:30:00+03:00`,
    type: types[(index + numericId) % types.length],
    subject,
    participants: participants.slice(0, 2 + (index % 2)),
    outcome: index === 1 ? 'Согласовали обновлённый план.' : 'Зафиксировали договорённости и следующие шаги.',
    nextAction: index === 2 ? 'Проверить комплект документов' : 'Подтвердить дату следующей встречи',
    dueDate: index === 0 ? '2026-09-28' : index === 2 ? '2026-09-25' : null,
    author: university.responsible?.name ?? 'Анна Иванова',
  }));
}

/** Typed frontend adapter for the future university responsibles endpoint. */
export async function getUniversityResponsibles(id: string): Promise<UniversityResponsibleContact[]> {
  const university = getUniversityOrThrow(id);
  const contacts: UniversityResponsibleContact[] = [
    { id: 'contact-anna', name: 'Анна Иванова', role: 'Координатор проекта', email: 'anna.ivanova@example.ru', phone: '+7 (900) 123-45-67', isPrimary: true, initials: 'АИ' },
    { id: 'contact-boris', name: 'Борис Петров', role: 'Руководитель направления', email: 'boris.petrov@example.ru', phone: '+7 (900) 234-56-78', isPrimary: false, initials: 'БП' },
    { id: 'contact-elena', name: 'Елена Смирнова', role: 'Методист', email: 'elena.smirnova@example.ru', phone: '+7 (900) 345-67-89', isPrimary: false, initials: 'ЕС' },
  ];
  if (university.responsible) contacts[0] = { ...contacts[0], name: university.responsible.name, initials: university.responsible.name.split(' ').map((part) => part[0]).join('').slice(0, 2).toLocaleUpperCase('ru-RU') };
  return contacts;
}
