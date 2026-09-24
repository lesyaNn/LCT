/** One query-key factory for every server-state family. */
export const queryKeys = {
  dashboard: {
    overview: ['dashboard-overview'] as const,
    analytics: ['dashboard-analytics'] as const,
  },
  universities: {
    all: ['universities'] as const,
    list: <T>(query: T) => ['universities', query] as const,
    passport: (id: string) => ['university-passport', id] as const,
    workflow: (instanceId: string) => ['workflow', instanceId] as const,
    workflowComments: (instanceId: string) => ['workflow', instanceId, 'comments'] as const,
    historyFamily: (id: string) => ['university-history', id] as const,
    history: <T>(id: string, filters: T) => ['university-history', id, filters] as const,
    healthScore: (id: string) => ['university-health-score', id] as const,
    healthScoreBatch: (ids: readonly string[]) => ['university-health-score-batch', [...ids].sort()] as const,
    programs: (id: string) => ['university-programs', id] as const,
    teachers: (id: string) => ['university-teachers', id] as const,
    students: (id: string) => ['university-students', id] as const,
    products: (id: string) => ['university-products', id] as const,
    licenses: (id: string) => ['university-licenses', id] as const,
    documents: (id: string) => ['university-documents', id] as const,
    meetings: (id: string) => ['university-meetings', id] as const,
    responsibles: (id: string) => ['university-responsibles', id] as const,
  },
  teachers: {
    passport: (id: string) => ['teacher-passport', id] as const,
  },
  reports: {
    all: ['reports'] as const,
    jobs: ['reports', 'jobs'] as const,
    job: (id: string) => ['reports', 'jobs', id] as const,
    filterOptions: ['reports', 'filter-options'] as const,
  },
  audit: {
    all: ['audit'] as const,
    list: <T>(query: T) => ['audit', query] as const,
  },
  workflowTemplates: {
    all: ['workflow-templates'] as const,
    lists: ['workflow-templates', 'list'] as const,
    list: (page = 1, pageSize = 100) => ['workflow-templates', 'list', page, pageSize] as const,
    detail: (templateId: string) => ['workflow-templates', 'detail', templateId] as const,
  },
  imports: {
    all: ['imports'] as const,
    preview: (fileId: string) => ['imports', 'preview', fileId] as const,
    jobs: ['imports', 'jobs'] as const,
    job: (id: string) => ['imports', 'jobs', id] as const,
  },
  users: {
    all: ['users'] as const,
    list: <T>(query: T) => ['users', 'list', query] as const,
    detail: (id: string) => ['users', 'detail', id] as const,
    responsibleCandidates: ['users', 'responsible-candidates'] as const,
    access: ['users', 'access'] as const,
  },
} as const;
