import { getHealthStatus, type HealthStatus } from './health-score';
import { programStatusLabels, type ProgramStatus } from './dashboard-repository';

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
}

export type UniversitySortColumn = 'name' | 'responsible' | 'programs' | 'stage' | 'health_score' | 'last_interaction';
export type SortOrder = 'asc' | 'desc';

export interface UniversityListQuery {
  search: string;
  city: string;
  responsible: string;
  healthStatuses: HealthStatus[];
  stage: string;
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
};

function compareValues(left: string | number, right: string | number): number {
  if (typeof left === 'number' && typeof right === 'number') return left - right;
  return String(left).localeCompare(String(right), 'ru', { sensitivity: 'base' });
}

export async function getUniversities(params: UniversityListQuery): Promise<PaginatedResult<UniversityListItem>> {
  const search = params.search.trim().toLocaleLowerCase('ru-RU');
  let filtered = universitiesMock.filter((item) => {
    if (search && !item.name.toLocaleLowerCase('ru-RU').includes(search)) return false;
    if (params.city && item.city !== params.city) return false;
    if (params.responsible && item.responsible?.id !== params.responsible) return false;
    if (params.stage && item.currentStage.id !== params.stage) return false;
    if (params.healthStatuses.length && !params.healthStatuses.includes(getHealthStatus(item.healthScore))) return false;
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
