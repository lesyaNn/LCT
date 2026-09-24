/**
 * P5-12-02: сохраняемые фильтры (sessionStorage, без новых зависимостей).
 *
 * Zero-dep эквивалент zustand/persist-стора из задачи: фильтры переживают
 * перезагрузку страницы, чистятся при закрытии вкладки (sessionStorage —
 * безопасно для приватности). Приватные данные (токены, профиль) здесь
 * никогда не хранятся — только фильтры списков.
 */

export interface UnifiedFilter {
  date_from: string | null;
  date_to: string | null;
  university_ids: string[];
  direction_ids: string[];
  program_ids: string[];
  product_ids: string[];
  responsible_ids: string[];
  workflow_statuses: string[];
}

const STORAGE_KEY = "crm-filters";
const SCOPE = "universities";

export const defaultFilter: UnifiedFilter = {
  date_from: null,
  date_to: null,
  university_ids: [],
  direction_ids: [],
  program_ids: [],
  product_ids: [],
  responsible_ids: [],
  workflow_statuses: [],
};

type Listener = () => void;
const listeners = new Set<Listener>();

function read(): UnifiedFilter {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...defaultFilter };
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const scope = parsed[SCOPE];
    if (typeof scope !== "object" || scope === null) return { ...defaultFilter };
    return { ...defaultFilter, ...(scope as Partial<UnifiedFilter>) };
  } catch {
    return { ...defaultFilter };
  }
}

function write(filter: UnifiedFilter): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ [SCOPE]: filter }));
  } catch {
    // sessionStorage недоступен (SSR/приватный режим) — работаем в памяти
  }
  listeners.forEach((l) => l());
}

export function getUniversitiesFilter(): UnifiedFilter {
  return read();
}

export function setUniversitiesFilter(patch: Partial<UnifiedFilter>): void {
  write({ ...read(), ...patch });
}

export function resetUniversitiesFilter(): void {
  write({ ...defaultFilter });
}

/** Подписка на изменения (для ручного subscribe без zustand). */
export function subscribeFilters(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
