import type { QueryClient } from '@tanstack/react-query';
import { dashboardAnalyticsQueryKey, dashboardQueryKey } from './dashboard-repository';
import {
  universityHealthScoreQueryKey,
  universityHistoryFamilyQueryKey,
  universityPassportQueryKey,
  universitiesQueryKey,
  workflowQueryKey,
} from './universities-repository';

export function invalidateWorkflowDetail(queryClient: QueryClient, instanceId: string): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) });
}

/**
 * Mark only the server-state representations affected by a workflow transition
 * as stale. Query families are addressed by their existing prefixes, so every
 * filter/sort/page variant of the universities list is covered without touching
 * unrelated application cache entries.
 */
export function invalidateWorkflowRelatedQueries(queryClient: QueryClient, instanceId: string, universityId?: string | null): Promise<unknown[]> {
  const invalidations = [
    invalidateWorkflowDetail(queryClient, instanceId),
    queryClient.invalidateQueries({ queryKey: universitiesQueryKey }),
    queryClient.invalidateQueries({ queryKey: dashboardQueryKey }),
    queryClient.invalidateQueries({ queryKey: dashboardAnalyticsQueryKey }),
  ];

  if (universityId) {
    invalidations.push(
      queryClient.invalidateQueries({ queryKey: universityPassportQueryKey(universityId) }),
      queryClient.invalidateQueries({ queryKey: universityHealthScoreQueryKey(universityId) }),
      queryClient.invalidateQueries({ queryKey: universityHistoryFamilyQueryKey(universityId) }),
    );
  }

  return Promise.all(invalidations);
}
