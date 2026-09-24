'use client';

export type DataSourceMode = 'mock' | 'real';

const mockRequested = process.env.NEXT_PUBLIC_DATA_SOURCE === 'mock';
const mockAllowed = process.env.NODE_ENV !== 'production'
  || process.env.NEXT_PUBLIC_ALLOW_MOCK_API_IN_PRODUCTION === 'true'
  // Explicit mock auth is the local demo switch used by Docker preview runs.
  || process.env.NEXT_PUBLIC_AUTH_MODE === 'mock';

/**
 * Public, build-time Next.js data-source selection.
 *
 * Real API is fail-safe: a production bundle ignores `mock` unless the
 * dedicated production opt-in is also present. Components never read these
 * variables directly; repositories are the only selection boundary.
 */
export const DATA_SOURCE_MODE: DataSourceMode = mockRequested && mockAllowed ? 'mock' : 'real';
export const isMockDataSource = DATA_SOURCE_MODE === 'mock';

const configuredDelay = Number(process.env.NEXT_PUBLIC_MOCK_API_DELAY_MS ?? 350);
export const MOCK_API_DELAY_MS = Number.isFinite(configuredDelay)
  ? Math.min(2_000, Math.max(0, configuredDelay))
  : 350;

function abortError(): DOMException {
  return new DOMException('Запрос отменён', 'AbortError');
}

export async function waitForMockDelay(signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) throw abortError();
  if (MOCK_API_DELAY_MS === 0) return;

  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      resolve();
    }, MOCK_API_DELAY_MS);
    const abort = () => {
      clearTimeout(timeout);
      reject(abortError());
    };
    signal?.addEventListener('abort', abort, { once: true });
  });
}

export async function mockRequest<T>(factory: () => T | Promise<T>, signal?: AbortSignal): Promise<T> {
  await waitForMockDelay(signal);
  if (signal?.aborted) throw abortError();
  return factory();
}

export async function fromDataSource<T>(implementations: {
  mock: () => T | Promise<T>;
  real: () => T | Promise<T>;
  signal?: AbortSignal;
}): Promise<T> {
  if (isMockDataSource) return mockRequest(implementations.mock, implementations.signal);
  return implementations.real();
}
