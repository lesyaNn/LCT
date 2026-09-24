import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
import { getExternalDashboardMetrics } from './external-integrations-repository';

export interface DashboardOverview {
  universitiesTotal: number | null;
  averageHealthScore: number | null;
  redUniversities: number | null;
  overdueStages: number | null;
  expiringLicenses: number | null;
  activePrograms: number | null;
  teachersNeedUpgrade: number | null;
  websiteApplications7d: number | null;
  lmsStudents: number | null;
  websiteSyncedAt: string | null;
  lmsSyncedAt: string | null;
}

export type HealthScoreRange = '0–20' | '21–40' | '41–60' | '61–80' | '81–100';

export interface HealthScoreDistributionItem {
  range: HealthScoreRange;
  count: number;
  tone: 'danger' | 'warning' | 'brand' | 'success';
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
  healthScoreDistribution: HealthScoreDistributionItem[];
  programStatuses: ProgramStatusItem[];
  launchDynamics: LaunchDynamicsItem[];
  attentionItems: AttentionItem[];
}

export const dashboardQueryKey = queryKeys.dashboard.overview;
export const dashboardAnalyticsQueryKey = queryKeys.dashboard.analytics;

/**
 * Temporary fixture for the first frontend slice. The function is the single
 * replacement point for the future analytics API adapter (`GET /analytics/overview`
 * with the university count sourced from `GET /universities?page_size=1`).
 */
const dashboardOverviewMock: DashboardOverview = {
  universitiesTotal: 42,
  averageHealthScore: 78.4,
  redUniversities: 5,
  overdueStages: 12,
  expiringLicenses: 8,
  activePrograms: 24,
  teachersNeedUpgrade: 17,
  websiteApplications7d: 38,
  lmsStudents: 126,
  websiteSyncedAt: '2026-09-24T08:45:00.000Z',
  lmsSyncedAt: '2026-09-24T08:45:00.000Z',
};

type CatalogOverviewApi = {
  total_universities?: number;
  rows?: Array<{ expires_at?: string | null }>;
  directions?: Array<{ programs?: number }>;
};

async function getCatalogOverview(): Promise<CatalogOverviewApi> {
  const result = await apiFetch<CatalogOverviewApi>('/api/v1/catalog/overview?page=1&page_size=100');
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить обзор Dashboard.', result.error);
  return result.data;
}

async function getRealDashboardOverview(): Promise<DashboardOverview> {
  const [overview, integration] = await Promise.all([getCatalogOverview(), getExternalDashboardMetrics()]);
  const expiryThreshold = new Date();
  expiryThreshold.setDate(expiryThreshold.getDate() + 30);
  const expiringLicenses = (overview.rows ?? []).filter((row) => {
    if (!row.expires_at) return false;
    const expiresAt = new Date(row.expires_at);
    return Number.isFinite(expiresAt.getTime()) && expiresAt >= new Date() && expiresAt <= expiryThreshold;
  }).length;
  return {
    universitiesTotal: overview.total_universities ?? 0,
    averageHealthScore: null,
    redUniversities: null,
    overdueStages: null,
    expiringLicenses,
    activePrograms: (overview.directions ?? []).reduce((sum, direction) => sum + (direction.programs ?? 0), 0),
    teachersNeedUpgrade: null,
    websiteApplications7d: integration.websiteApplications7d,
    lmsStudents: integration.lmsStudents,
    websiteSyncedAt: integration.websiteSyncedAt,
    lmsSyncedAt: integration.lmsSyncedAt,
  };
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  return fromDataSource({ mock: () => dashboardOverviewMock, real: getRealDashboardOverview });
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
  healthScoreDistribution: [
    { range: '0–20', count: 2, tone: 'danger' },
    { range: '21–40', count: 3, tone: 'danger' },
    { range: '41–60', count: 8, tone: 'warning' },
    { range: '61–80', count: 17, tone: 'brand' },
    { range: '81–100', count: 12, tone: 'success' },
  ],
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
    { id: 'attention-003', universityId: 'university-003', universityName: 'Уральский федеральный университет', problemCode: 'HEALTH-LOW', problemLabel: 'Низкий Health Score', severity: 'yellow', overdueDays: 9 },
    { id: 'attention-004', universityId: 'university-004', universityName: 'Казанский федеральный университет', problemCode: 'TEACH-READINESS', problemLabel: 'Преподаватели требуют повышения', severity: 'orange', overdueDays: 7 },
    { id: 'attention-005', universityId: 'university-005', universityName: 'Новосибирский государственный университет', problemCode: 'DOC-MISSING', problemLabel: 'Не хватает документов', severity: 'yellow', overdueDays: 4 },
  ],
};

async function getRealDashboardAnalytics(): Promise<DashboardAnalytics> {
  const overview = await getCatalogOverview();
  const activePrograms = (overview.directions ?? []).reduce((sum, direction) => sum + (direction.programs ?? 0), 0);
  return {
    healthScoreDistribution: [],
    programStatuses: activePrograms ? [{ status: 'active', label: programStatusLabels.active, count: activePrograms, tone: 'brand' }] : [],
    launchDynamics: [],
    attentionItems: [],
  };
}

export async function getDashboardAnalytics(): Promise<DashboardAnalytics> {
  return fromDataSource({ mock: () => dashboardAnalyticsMock, real: getRealDashboardAnalytics });
}
