export interface DashboardOverview {
  universitiesTotal: number | null;
  averageHealthScore: number | null;
  redUniversities: number | null;
  overdueStages: number | null;
  expiringLicenses: number | null;
  activePrograms: number | null;
  teachersNeedUpgrade: number | null;
}

export type HealthScoreRange = '0–20' | '21–40' | '41–60' | '61–80' | '81–100';

export interface HealthScoreDistributionItem {
  range: HealthScoreRange;
  count: number;
  tone: 'danger' | 'warning' | 'brand' | 'success';
}

export type ProgramStatus = 'planned' | 'active' | 'launched' | 'archived';

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

export const dashboardQueryKey = ['dashboard-overview'] as const;
export const dashboardAnalyticsQueryKey = ['dashboard-analytics'] as const;

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
};

export async function getDashboardOverview(): Promise<DashboardOverview> {
  return dashboardOverviewMock;
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
    { status: 'planned', label: 'Запланированы', count: 9, tone: 'neutral' },
    { status: 'active', label: 'Активны', count: 24, tone: 'brand' },
    { status: 'launched', label: 'Запущены', count: 7, tone: 'success' },
    { status: 'archived', label: 'Архивные', count: 2, tone: 'dark' },
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

export async function getDashboardAnalytics(): Promise<DashboardAnalytics> {
  return dashboardAnalyticsMock;
}
