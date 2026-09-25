'use client';

export type DataSourceMode = 'mock' | 'real';
export type DataSourceDomain = 'universities' | 'catalogs' | 'passport';

const mockRequested = process.env.NEXT_PUBLIC_DATA_SOURCE === 'mock';
const mockAllowed = process.env.NODE_ENV !== 'production'
  || process.env.NEXT_PUBLIC_ALLOW_MOCK_API_IN_PRODUCTION === 'true';

/**
 * Public, build-time Next.js data-source selection.
 *
 * Real API is fail-safe: a production bundle ignores `mock` unless the
 * dedicated production opt-in is also present. Components never read these
 * variables directly; repositories are the only selection boundary.
 */
export const DATA_SOURCE_MODE: DataSourceMode = mockRequested && mockAllowed ? 'mock' : 'real';
export const isMockDataSource = DATA_SOURCE_MODE === 'mock';

const realDomains = new Set(
  (process.env.NEXT_PUBLIC_REAL_API_DOMAINS ?? '')
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean),
);

/**
 * A small migration seam for resources that are already backed by the real
 * API while the rest of a local/demo build still uses fixtures. A domain can
 * only opt into `real`; it cannot force mock data into a real production
 * build.
 */
export function dataSourceModeFor(domain?: DataSourceDomain): DataSourceMode {
  if (domain && realDomains.has(domain)) return 'real';
  return DATA_SOURCE_MODE;
}

export function isMockDataSourceFor(domain: DataSourceDomain): boolean {
  return dataSourceModeFor(domain) === 'mock';
}

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
  domain?: DataSourceDomain;
}): Promise<T> {
  if (dataSourceModeFor(implementations.domain) === 'mock') {
    return mockRequest(implementations.mock, implementations.signal);
  }
  return implementations.real();
}
