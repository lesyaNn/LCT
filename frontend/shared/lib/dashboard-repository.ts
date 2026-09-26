import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
import { getExternalDashboardMetrics } from './external-integrations-repository';

export interface DashboardOverview {
  mode?: 'real' | 'mock' | 'import';
  universitiesTotal: number | null;
  overdueStages: number | null;
  expiringLicenses: number | null;
  activePrograms: number | null;
  launchedPrograms: number | null;
  websiteApplications7d: number | null;
  websiteSyncedAt: string | null;
}

export type ProgramStatus = 'planned' | 'active' | 'launched' | 'archived';

export const programStatusLabels: Record<ProgramStatus, string> = {
  planned: 'Запланированы',
  active: 'Активны',
  launched: 'Запущены',
  archived: 'Архивные',
};

export interface ProgramStatusItem {
  status: ProgramStatus;
  label: string;
  count: number;
  tone: 'neutral' | 'brand' | 'success' | 'dark';
}

export interface LaunchDynamicsItem {
  monthKey: string;
  monthLabel: string;
  actual: number;
  planned: number;
}

export type AttentionSeverity = 'red' | 'orange' | 'yellow';

export interface AttentionItem {
  id: string;
  universityId: string;
  universityName: string;
  problemCode: string;
  problemLabel: string;
  severity: AttentionSeverity;
  overdueDays: number;
}

export interface DashboardAnalytics {
  programStatuses: ProgramStatusItem[];
  launchDynamics: LaunchDynamicsItem[];
  attentionItems: AttentionItem[];
}

export interface DashboardFilters {
  dateFrom: string;
  dateTo: string;
  universityIds: string[];
  directionIds: string[];
  productIds: string[];
  responsibleIds: string[];
}

export const EMPTY_DASHBOARD_FILTERS: DashboardFilters = { dateFrom: '', dateTo: '', universityIds: [], directionIds: [], productIds: [], responsibleIds: [] };
export const dashboardQueryKey = queryKeys.dashboard.overview;
export const dashboardAnalyticsQueryKey = dashboardQueryKey;
export const dashboardDataQueryKey = (filters: DashboardFilters) => queryKeys.dashboard.data(filters);

/** Fixture used only when the application is configured for mock data. */
const dashboardOverviewMock: DashboardOverview = {
  mode: 'mock',
  universitiesTotal: 42,
  overdueStages: 12,
  expiringLicenses: 8,
  activePrograms: 24,
  launchedPrograms: 7,
  websiteApplications7d: 38,
  websiteSyncedAt: '2026-09-24T08:45:00.000Z',
};

type AnalyticsOverviewDto = {
  kpi: { universities: number; overdue_stages: number; expiring_licenses: number; active_programs: number; launched_programs: number };
  workflow_distribution: Array<{ stage: string; count: number }>;
  program_statuses: Array<{ status: string; count: number }>;
  launch_dynamics?: Array<{ month: string; actual: number; planned: number }>;
  overdue_items: Array<{ id?: string; university_id?: string | null; university: string; stage?: string | null; task?: string | null; days_overdue: number; type: 'stage' | 'task' }>;
};

function analyticsParams(filters: DashboardFilters): string {
  const params = new URLSearchParams();
  if (filters.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters.dateTo) params.set('date_to', filters.dateTo);
  for (const [key, values] of [
    ['university_ids', filters.universityIds], ['direction_ids', filters.directionIds],
    ['product_ids', filters.productIds], ['responsible_ids', filters.responsibleIds],
  ] as const) for (const value of values) params.append(key, value);
  return params.toString();
}

function mapDashboardOverview(dto: AnalyticsOverviewDto): DashboardOverview {
  return {
    universitiesTotal: dto.kpi.universities,
    overdueStages: dto.kpi.overdue_stages,
    expiringLicenses: dto.kpi.expiring_licenses,
    activePrograms: dto.kpi.active_programs,
    launchedPrograms: dto.kpi.launched_programs,
    websiteApplications7d: null,
    websiteSyncedAt: null,
  };
}

const monthFormatter = new Intl.DateTimeFormat('ru-RU', { month: 'short' });

function getRecentMonths(): LaunchDynamicsItem[] {
  const today = new Date();
  const actual = [8, 11, 7, 13, 10, 15, 12, 16, 14, 18, 17, 20];
  const planned = [10, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19, 22];

  return actual.map((actualCount, index) => {
    const month = new Date(today.getFullYear(), today.getMonth() - (11 - index), 1);
    const monthLabel = monthFormatter.format(month).replace('.', '');

    return {
      monthKey: `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}`,
      monthLabel: monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1),
      actual: actualCount,
      planned: planned[index],
    };
  });
}

const dashboardAnalyticsMock: DashboardAnalytics = {
  programStatuses: [
    { status: 'planned', label: programStatusLabels.planned, count: 9, tone: 'neutral' },
    { status: 'active', label: programStatusLabels.active, count: 24, tone: 'brand' },
    { status: 'launched', label: programStatusLabels.launched, count: 7, tone: 'success' },
    { status: 'archived', label: programStatusLabels.archived, count: 2, tone: 'dark' },
  ],
  launchDynamics: getRecentMonths(),
  attentionItems: [
    { id: 'attention-001', universityId: 'university-001', universityName: 'Московский технический университет связи и информатики', problemCode: 'LIC-EXP', problemLabel: 'Истекает лицензия', severity: 'red', overdueDays: 18 },
    { id: 'attention-002', universityId: 'university-002', universityName: 'Санкт-Петербургский политехнический университет', problemCode: 'WF-OVERDUE', problemLabel: 'Просрочен этап workflow', severity: 'orange', overdueDays: 12 },
    { id: 'attention-005', universityId: 'university-005', universityName: 'Новосибирский государственный университет', problemCode: 'DOC-MISSING', problemLabel: 'Не хватает документов', severity: 'yellow', overdueDays: 4 },
  ],
};

function mapDashboardAnalytics(overview: AnalyticsOverviewDto): DashboardAnalytics {
  const tones: Record<ProgramStatus, ProgramStatusItem['tone']> = { planned: 'neutral', active: 'brand', launched: 'success', archived: 'dark' };
  const monthFormatter = new Intl.DateTimeFormat('ru-RU', { month: 'short' });
  return {
    programStatuses: overview.program_statuses.filter((item): item is { status: ProgramStatus; count: number } => item.status in tones).map((item) => ({ status: item.status, label: programStatusLabels[item.status], count: item.count, tone: tones[item.status] })),
    launchDynamics: (overview.launch_dynamics ?? []).map((item) => { const date = new Date(`${item.month}-01T12:00:00`); return { monthKey: item.month, monthLabel: monthFormatter.format(date).replace('.', ''), actual: item.actual, planned: item.planned }; }),
    attentionItems: overview.overdue_items.filter((item) => Boolean(item.university_id)).slice(0, 5).map((item, index) => ({ id: item.id ?? `overdue-${index}`, universityId: item.university_id!, universityName: item.university, problemCode: item.type === 'stage' ? 'WF-OVERDUE' : 'TASK-OVERDUE', problemLabel: item.stage ?? item.task ?? 'Просрочено', severity: item.days_overdue > 14 ? 'red' : item.days_overdue > 7 ? 'orange' : 'yellow', overdueDays: item.days_overdue })),
  };
}

export interface DashboardData { overview: DashboardOverview; analytics: DashboardAnalytics }

export async function getDashboardData(filters: DashboardFilters = EMPTY_DASHBOARD_FILTERS): Promise<DashboardData> {
  return fromDataSource({
    mock: () => ({ overview: dashboardOverviewMock, analytics: dashboardAnalyticsMock }),
    real: async () => {
      const query = analyticsParams(filters);
      const [result, integration] = await Promise.all([
        apiFetch<AnalyticsOverviewDto>(`/api/v1/analytics/overview${query ? `?${query}` : ''}`),
        query ? Promise.resolve(null) : getExternalDashboardMetrics().catch(() => null),
      ]);
      if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить аналитику Dashboard.', result.error);
      return { overview: { ...mapDashboardOverview(result.data), ...(integration ?? {}) }, analytics: mapDashboardAnalytics(result.data) };
    },
  });
}
