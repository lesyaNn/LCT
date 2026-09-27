import type { UserRole } from '@/shared/types/user';
import { ApiRequestError } from './api-errors';
import { fromDataSource, isMockDataSourceFor } from './data-source';
import { queryKeys } from './query-keys';
import {
  mockCreateCatalogItem,
  mockGetCatalogItem,
  mockGetCatalogReferenceData,
  mockListCatalogItems,
  mockSetCatalogItemActive,
  mockUpdateCatalogItem,
} from '@/shared/mocks/api-adapter';
import {
  realCreateCatalogItem,
  realGetCatalogItem,
  realGetCatalogReferenceData,
  realListCatalogItems,
  realSetCatalogItemActive,
  realUpdateCatalogItem,
} from './real-api-adapter';

export type CatalogType = 'universities' | 'products' | 'directions' | 'responsibles';

interface CatalogItemBase {
  id: string;
  type: CatalogType;
  name: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface UniversityCatalogItem extends CatalogItemBase {
  type: 'universities';
  city: string;
}

export interface ProductCatalogItem extends CatalogItemBase {
  type: 'products';
  vendorId: string;
  vendorName: string;
  programId: string;
  programName: string;
  version: string;
  contacts?: Array<{ id: string; fullName: string; email: string; phone: string; communicationMethod: string }>;
}

export interface DirectionCatalogItem extends CatalogItemBase {
  type: 'directions';
  code: string;
}

export interface ResponsibleCatalogItem extends CatalogItemBase {
  type: 'responsibles';
  email: string;
  phone: string;
  role: string;
  universityIds: string[];
}

export type CatalogItem = UniversityCatalogItem | ProductCatalogItem | DirectionCatalogItem | ResponsibleCatalogItem;

export type CatalogInput =
  | { type: 'universities'; name: string; city: string }
  | { type: 'products'; name: string; vendorId: string; programId: string; version: string }
  | { type: 'directions'; name: string; code: string }
  | { type: 'responsibles'; name: string; email: string; phone: string; role: string; universityIds: string[] };

export interface CatalogListQuery {
  type: CatalogType;
  search: string;
  showInactive: boolean;
  page: number;
  pageSize: number;
}

export interface CatalogListResult {
  items: CatalogItem[];
  page: number;
  pageSize: number;
  total: number;
}

export interface CatalogReferenceOption {
  id: string;
  name: string;
  description?: string;
}

export interface CatalogReferenceData {
  vendors: CatalogReferenceOption[];
  universities: CatalogReferenceOption[];
  products: CatalogReferenceOption[];
  directions: CatalogReferenceOption[];
  programs: CatalogReferenceOption[];
  responsibles: CatalogReferenceOption[];
}

export const catalogDefinitions: ReadonlyArray<{ id: CatalogType; label: string; singular: string; searchPlaceholder: string }> = [
  { id: 'universities', label: 'Вузы', singular: 'ВУЗ', searchPlaceholder: 'Название или город' },
  { id: 'products', label: 'Продукты', singular: 'продукт', searchPlaceholder: 'Название продукта' },
  { id: 'directions', label: 'Направления', singular: 'направление', searchPlaceholder: 'Название или код' },
  { id: 'responsibles', label: 'Ответственные', singular: 'ответственного', searchPlaceholder: 'ФИО или email' },
] as const;

export const catalogQueryKeys = {
  all: queryKeys.catalogs.all,
  family: queryKeys.catalogs.family,
  list: queryKeys.catalogs.list,
  detail: queryKeys.catalogs.detail,
  references: queryKeys.catalogs.references,
};

export const CATALOG_API_CAPABILITIES = isMockDataSourceFor('catalogs')
  ? { softActivation: true, inactiveFilter: true, mutationRoles: ['admin', 'manager'] as UserRole[] }
  : { softActivation: false, inactiveFilter: false, mutationRoles: ['admin', 'manager'] as UserRole[] };

export function canMutateCatalog(role: UserRole | undefined): boolean {
  return Boolean(role && CATALOG_API_CAPABILITIES.mutationRoles.includes(role));
}

export function catalogDefinition(type: CatalogType) {
  return catalogDefinitions.find((item) => item.id === type) ?? catalogDefinitions[0];
}

export function isCatalogType(value: unknown): value is CatalogType {
  return catalogDefinitions.some((item) => item.id === value);
}

export async function listCatalogItems(query: CatalogListQuery, signal?: AbortSignal): Promise<CatalogListResult> {
  return fromDataSource({ domain: 'catalogs', signal, mock: () => mockListCatalogItems(query), real: () => realListCatalogItems(query, signal) });
}

export async function getCatalogItem(type: CatalogType, id: string, signal?: AbortSignal): Promise<CatalogItem> {
  return fromDataSource({ domain: 'catalogs', signal, mock: () => mockGetCatalogItem(type, id), real: () => realGetCatalogItem(type, id, signal) });
}

export async function getCatalogReferenceData(signal?: AbortSignal): Promise<CatalogReferenceData> {
  return fromDataSource({ domain: 'catalogs', signal, mock: mockGetCatalogReferenceData, real: () => realGetCatalogReferenceData(signal) });
}

export async function createCatalogItem(input: CatalogInput): Promise<CatalogItem> {
  return fromDataSource({ mock: () => mockCreateCatalogItem(input), real: () => realCreateCatalogItem(input) });
}

export async function updateCatalogItem(id: string, input: CatalogInput): Promise<CatalogItem> {
  return fromDataSource({ mock: () => mockUpdateCatalogItem(id, input), real: () => realUpdateCatalogItem(id, input) });
}

export async function setCatalogItemActive(type: CatalogType, id: string, active: boolean): Promise<CatalogItem> {
  if (!CATALOG_API_CAPABILITIES.softActivation) {
    throw new ApiRequestError(501, { code: 'CATALOG_SOFT_DELETE_UNAVAILABLE' }, 'Backend не поддерживает безопасную активацию каталогов.');
  }
  return fromDataSource({ mock: () => mockSetCatalogItemActive(type, id, active), real: () => realSetCatalogItemActive(type, id, active) });
}

export function relatedCatalogQueryKeys(type: CatalogType, id?: string): ReadonlyArray<readonly unknown[]> {
  const keys: Array<readonly unknown[]> = [
    queryKeys.catalogs.family(type),
    queryKeys.catalogs.references,
    queryKeys.reports.filterOptions,
  ];
  if (type === 'universities') {
    keys.push(queryKeys.universities.all, queryKeys.universities.passports);
    if (id) keys.push(queryKeys.universities.passport(id));
  }
  if (type === 'products') keys.push(queryKeys.universities.productsAll, queryKeys.universities.passports);
  if (type === 'directions') keys.push(queryKeys.universities.programsAll, queryKeys.universities.passports);
  if (type === 'responsibles') keys.push(queryKeys.users.responsibleCandidates, queryKeys.universities.responsiblesAll, queryKeys.universities.passports);
  return keys;
}
