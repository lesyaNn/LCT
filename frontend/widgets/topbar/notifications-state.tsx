'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { ApiRequestError, normalizeApiError } from '@/shared/lib/api-errors';
import { notificationsRepository, type NotificationFilter } from '@/shared/lib/notifications-repository';
import { queryKeys } from '@/shared/lib/query-keys';

interface Options {
  filter?: NotificationFilter;
  limit?: number;
  offset?: number;
  enabled?: boolean;
}

export function useNotifications({ filter = 'all', limit = 7, offset = 0, enabled = true }: Options = {}) {
  const { user } = useAuth();
  const userId = user?.id ?? '';
  const queryClient = useQueryClient();
  const listQuery = useQuery({
    queryKey: queryKeys.notifications.list(userId, filter, limit, offset),
    queryFn: async ({ signal }) => {
      const result = await notificationsRepository.list(filter, limit, offset, signal);
      if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить уведомления.', result.error);
      return result.data;
    },
    enabled: Boolean(userId) && enabled,
    staleTime: 20_000,
    refetchInterval: enabled ? 45_000 : false,
    retry: false,
  });
  const countQuery = useQuery({
    queryKey: queryKeys.notifications.count(userId),
    queryFn: async ({ signal }) => {
      const result = await notificationsRepository.unreadCount(signal);
      if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить количество уведомлений.', result.error);
      return result.data.count;
    },
    enabled: Boolean(userId),
    staleTime: 20_000,
    refetchInterval: 45_000,
    retry: false,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications.user(userId) });
  const readMutation = useMutation({
    mutationFn: async (id: string) => {
      const result = await notificationsRepository.markRead(id);
      if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось отметить уведомление прочитанным.', result.error);
    },
    onSuccess: invalidate,
    retry: false,
  });
  const readAllMutation = useMutation({
    mutationFn: async () => {
      const result = await notificationsRepository.markAllRead();
      if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось отметить уведомления прочитанными.', result.error);
      return result.data.updated;
    },
    onSuccess: invalidate,
    retry: false,
  });

  const error = listQuery.error ?? countQuery.error;
  return {
    items: listQuery.data?.items ?? [],
    total: listQuery.data?.total ?? 0,
    unreadCount: countQuery.data ?? 0,
    loading: enabled && listQuery.isPending && listQuery.isFetching,
    error: error ? normalizeApiError(error, { fallbackMessage: 'Не удалось загрузить уведомления. Попробуйте ещё раз.' }).message : '',
    refresh: async () => { await Promise.all([listQuery.refetch(), countQuery.refetch()]); },
    markRead: readMutation.mutateAsync,
    markAllRead: readAllMutation.mutateAsync,
    markingAll: readAllMutation.isPending,
  };
}
