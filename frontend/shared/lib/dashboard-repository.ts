export interface DashboardOverview {
  universitiesTotal: number | null;
  averageHealthScore: number | null;
  redUniversities: number | null;
  overdueStages: number | null;
  expiringLicenses: number | null;
  activePrograms: number | null;
  teachersNeedUpgrade: number | null;
}

export const dashboardQueryKey = ['dashboard-overview'] as const;

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
