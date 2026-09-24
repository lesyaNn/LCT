import { isMockDataSource } from './data-source';
import { queryKeys } from './query-keys';
import { getUniversityExternalData } from './external-integrations-repository';
import {
  getUniversities,
  getUniversityPassport,
  getUniversityWorkflow,
  type UniversityResponsible,
  type UniversityWorkflow,
  type UniversityWorkflowStage,
  type UniversityListItem,
} from './universities-repository';

export interface WorkflowOverviewItem {
  instanceId: string;
  universityId: string;
  universityName: string;
  programName: string | null;
  programKey: string | null;
  responsible: UniversityResponsible | null;
  workflow: UniversityWorkflow;
  stage: UniversityWorkflowStage;
  stageKey: string;
  status: 'in_progress' | 'completed' | 'overdue';
}

export interface WorkflowOverview {
  items: WorkflowOverviewItem[];
  unavailableUniversities: number;
  limited: boolean;
}

export const workflowOverviewQueryKey = queryKeys.universities.workflowOverview;

const emptyFilters = {
  search: '', city: '', universityIds: [], programIds: [], productIds: [], responsibleIds: [],
  healthStatuses: [], workflowStageId: '', dateFrom: '', dateTo: '',
};

async function universityInstances(university: UniversityListItem): Promise<WorkflowOverviewItem[]> {
  const [passportResult, applicationsResult] = await Promise.allSettled([
    isMockDataSource ? Promise.resolve(null) : getUniversityPassport(university.id),
    getUniversityExternalData(university.id, 'website'),
  ]);
  const passport = passportResult.status === 'fulfilled' ? passportResult.value : null;
  const applications = applicationsResult.status === 'fulfilled' ? applicationsResult.value?.applications ?? [] : [];
  const links = new Map<string, { name: string | null; key: string | null }>();
  if (isMockDataSource) links.set(university.id, { name: null, key: null });
  else if (passport?.workflow.currentStage.id && passport.workflow.currentStage.id !== 'not-started') {
    links.set(passport.workflow.currentStage.id, { name: null, key: null });
  }
  for (const application of applications) {
    if (application.workflowInstanceId) links.set(application.workflowInstanceId, { name: application.programName, key: application.id });
  }
  const entries = await Promise.allSettled([...links].map(async ([instanceId, program]) => {
    const workflow = await getUniversityWorkflow(instanceId);
    const stage = workflow.currentStage ?? workflow.stages.at(-1);
    if (!stage) return null;
    const templateId = workflow.templateId ?? 'unknown-template';
    return {
      instanceId,
      universityId: university.id,
      universityName: university.name,
      programName: program.name,
      programKey: program.key,
      responsible: passport?.workflow.responsible ?? university.responsible,
      workflow,
      stage,
      stageKey: `${templateId}:${stage.templateStageId ?? `${stage.orderIndex}:${stage.name}`}`,
      status: stage.status === 'overdue' ? 'overdue' : workflow.completedSteps >= workflow.totalSteps ? 'completed' : 'in_progress',
    } satisfies WorkflowOverviewItem;
  }));
  return entries.flatMap((entry) => entry.status === 'fulfilled' && entry.value ? [entry.value] : []);
}

/** Aggregate only instance IDs actually exposed by existing university/passport and website APIs. */
export async function getWorkflowOverview(): Promise<WorkflowOverview> {
  const page = await getUniversities({ filters: emptyFilters, sort: 'name', order: 'asc', page: 1, pageSize: 100 });
  const results = await Promise.allSettled(page.items.map(universityInstances));
  return {
    items: results.flatMap((result) => result.status === 'fulfilled' ? result.value : []),
    unavailableUniversities: results.filter((result) => result.status === 'rejected').length,
    limited: page.total > page.items.length,
  };
}
