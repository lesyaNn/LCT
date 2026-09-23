/**
 * P5-12-02: frontend-кэш без новых зависимостей.
 *
 * Zero-dep эквивалент TanStack Query-конфигурации из задачи:
 * staleTime 30s / gcTime 5min / retry 2 / без refetch при фокусе окна.
 * При переходе на `@tanstack/react-query` этот модуль заменяется на
 * QueryClient с теми же ключами (см. `queryKeys` ниже) и теми же точками
 * инвалидации — контракт ключей уже совпадает с backend.
 */

export type QueryKey = readonly unknown[];

type CacheEntry<T> = {
  data: T;
  freshUntil: number;
  keepUntil: number;
};

const STALE_TIME_MS = 30_000;
const GC_TIME_MS = 5 * 60_000;
const MAX_RETRIES = 2;

const store = new Map<string, CacheEntry<unknown>>();

function serialize(key: QueryKey): string {
  return JSON.stringify(key);
}

function gc(): void {
  const now = Date.now();
  for (const [k, v] of store) {
    if (v.keepUntil <= now) store.delete(k);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Запрос с кэшем: fresh — из кэша, иначе fetch с ретраями. */
export async function cachedQuery<T>(
  key: QueryKey,
  fetcher: () => Promise<T>,
  opts: { staleTime?: number; retries?: number } = {},
): Promise<T> {
  gc();
  const k = serialize(key);
  const now = Date.now();
  const hit = store.get(k) as CacheEntry<T> | undefined;
  if (hit && hit.freshUntil > now) return hit.data;

  const retries = opts.retries ?? MAX_RETRIES;
  let lastError: unknown = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const data = await fetcher();
      store.set(k, {
        data,
        freshUntil: now + (opts.staleTime ?? STALE_TIME_MS),
        keepUntil: now + GC_TIME_MS,
      });
      return data;
    } catch (e) {
      lastError = e;
      await sleep(Math.min(1000 * 2 ** attempt, 30_000));
    }
  }
  if (hit) return hit.data; // stale-while-error: отдаём протухшее, а не падаем
  throw lastError;
}

/** Инвалидация по префиксу ключа (вызывать после мутаций). */
export function invalidateQueries(prefix: QueryKey): void {
  const raw = serialize(prefix);
  const stem = raw.endsWith("]") ? raw.slice(0, -1) : raw;
  for (const k of [...store.keys()]) {
    if (k === raw || k.startsWith(stem + ",")) store.delete(k);
  }
}

/** Фабрика ключей — совпадает с backend-сущностями. */
export const queryKeys = {
  universities: (filters: unknown, pagination: unknown) =>
    ["universities", filters, pagination] as const,
  universityPassport: (id: string, include: unknown) =>
    ["university-passport", id, include] as const,
  teacherPassport: (id: string) => ["teacher-passport", id] as const,
  workflowInstance: (id: string) => ["workflow", id] as const,
  healthScore: (id: string) => ["health-score", id] as const,
  healthScoreBatch: (ids: readonly string[]) =>
    ["health-score", "batch", ids] as const,
  analyticsOverview: (filters: unknown) => ["analytics", filters] as const,
  reportJob: (id: string) => ["report", id] as const,
};

/** Паттерны инвалидации после мутаций (вызывать в onSuccess). */
export function invalidateAfterTransition(
  instanceId: string,
  universityId: string,
): void {
  invalidateQueries(["workflow", instanceId]);
  invalidateQueries(["health-score", universityId]);
  invalidateQueries(["universities"]);
  invalidateQueries(["analytics"]);
}

/** Тестовый шов: очистить весь кэш. */
export function __clearQueryCacheForTests(): void {
  store.clear();
}
