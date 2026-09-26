import { isMockDataSource, isMockDataSourceFor } from './data-source';
import { queryKeys } from './query-keys';
import { getUniversityExternalData } from './external-integrations-repository';
import {
  getUniversities,
  getUniversityPassport,
  getUniversityWorkflow,
  getApiUniversityWorkflow,
  listWorkflowInstancePage,
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

export function workflowStageKey(workflow: UniversityWorkflow, stage: UniversityWorkflowStage): string {
  return `${workflow.templateId ?? 'unknown-template'}:${stage.templateStageId ?? `${stage.orderIndex}:${stage.name}`}`;
}

const emptyFilters = {
  search: '', city: '', externalSource: '' as const, universityIds: [], programIds: [], productIds: [], responsibleIds: [],
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
    return {
      instanceId,
      universityId: university.id,
      universityName: university.name,
      programName: program.name,
      programKey: program.key,
      responsible: passport?.workflow.responsible ?? university.responsible,
      workflow,
      stage,
      stageKey: workflowStageKey(workflow, stage),
      status: stage.status === 'overdue' ? 'overdue' : workflow.stages.every((step) => step.status === 'completed' || step.status === 'skipped') ? 'completed' : 'in_progress',
    } satisfies WorkflowOverviewItem;
  }));
  return entries.flatMap((entry) => entry.status === 'fulfilled' && entry.value ? [entry.value] : []);
}

/** Aggregate only instance IDs actually exposed by existing university/passport and website APIs. */
export async function getWorkflowOverview(): Promise<WorkflowOverview> {
  if (!isMockDataSourceFor('workflow')) {
    const page = await listWorkflowInstancePage(1, 100);
    const items = page.items.flatMap((record) => {
      const workflow = getApiUniversityWorkflow(record);
      const stage = workflow.currentStage ?? workflow.stages.at(-1);
      return stage ? [{
        instanceId: record.id,
        universityId: record.university_id,
        universityName: record.university_name ?? record.university_id,
        programName: record.program_name ?? null,
        programKey: record.program_id ?? null,
        responsible: null,
        workflow,
        stage,
        stageKey: workflowStageKey(workflow, stage),
        status: stage.status === 'overdue' ? 'overdue' as const : record.status === 'completed' ? 'completed' as const : 'in_progress' as const,
      }] : [];
    });
    return { items, unavailableUniversities: 0, limited: page.total > page.items.length };
  }
  const page = await getUniversities({ filters: emptyFilters, sort: 'name', order: 'asc', page: 1, pageSize: 100 });
  const results = await Promise.allSettled(page.items.map(universityInstances));
  return {
    items: results.flatMap((result) => result.status === 'fulfilled' ? result.value : []),
    unavailableUniversities: results.filter((result) => result.status === 'rejected').length,
    limited: page.total > page.items.length,
  };
}
