import type { QueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/shared/lib/query-keys';
import { universityPassportQueryKey, universityResponsiblesQueryKey } from '@/shared/lib/universities-repository';

export async function invalidateResponsibleQueries(queryClient: QueryClient, id: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: universityPassportQueryKey(id) }),
    queryClient.invalidateQueries({ queryKey: universityResponsiblesQueryKey(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.universities.historyFamily(id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.universities.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowOverview }),
    queryClient.invalidateQueries({ queryKey: queryKeys.audit.all }),
  ]);
}
