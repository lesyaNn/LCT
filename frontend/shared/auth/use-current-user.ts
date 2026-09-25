'use client';

import { useQuery } from '@tanstack/react-query';
import { getCurrentUser } from '@/shared/lib/current-user-repository';
import { queryKeys } from '@/shared/lib/query-keys';

export function useCurrentUser(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.auth.me,
    queryFn: getCurrentUser,
    enabled: options.enabled ?? true,
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
}
