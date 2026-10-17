import type { AuthUser } from '@/shared/types/user';
import { hasPermission } from './access-control';
import { ApiRequestError } from './api-errors';
import { apiDownload, apiFetch, apiUploadFormData } from './api-client';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
import {
  mockCreateCatalogItem,
  mockDeleteCatalogItem,
  mockGetCatalogItem,
  mockGetCatalogReferenceData,
  mockListCatalogItems,
  mockUpdateCatalogItem,
} from '@/shared/mocks/api-adapter';
import {
  realCreateCatalogItem,
  realDeleteCatalogItem,
  realGetCatalogItem,
  realGetCatalogReferenceData,
  realListCatalogItems,
  realUpdateCatalogItem,
} from './real-api-adapter';

export type CatalogType = 'universities' | 'products' | 'vendors' | 'directions' | 'programs' | 'responsibles' | 'agreements';

/** Two business records share the "Договоры и лицензии" tab. */
export type AgreementKind = 'contracts' | 'licenses';

/** Contract lifecycle states stored in the DB; effective status is derived. */
export type ContractStatusRaw = 'draft' | 'signed' | 'terminated';

/** Derived on the server (app/services/license_status.py), never stored. */
export type AgreementStatus = 'draft' | 'signed' | 'active' | 'expired' | 'terminated' | 'expires_soon';

export type TransferStatus = 'pending' | 'transferred' | 'accepted' | 'rejected';

interface CatalogItemBase {
  id: string;
  type: CatalogType;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export interface CatalogContact {
  id: string;
  productId?: string | null;
  fullName: string;
  email: string;
  phone: string;
  communicationMethod: string;
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
  contacts?: CatalogContact[];
}

export interface DirectionCatalogItem extends CatalogItemBase {
  type: 'directions';
  code: string;
}

export interface ProgramCatalogItem extends CatalogItemBase {
  type: 'programs';
  directionId: string;
  directionName: string;
  description: string;
}

export interface VendorCatalogItem extends CatalogItemBase {
  type: 'vendors';
  contacts?: CatalogContact[];
}

export interface ResponsibleCatalogItem extends CatalogItemBase {
  type: 'responsibles';
  email: string;
  phone: string;
  role: string;
  universityIds: string[];
}

export interface ContractCatalogItem extends CatalogItemBase {
  type: 'agreements';
  kind: 'contracts';
  contractNumber: string;
  universityId: string;
  universityName: string;
  productId: string;
  productName: string;
  /** Resolved through the product: contracts have no vendor column. */
  vendorName: string;
  signedAt: string;
  expiresAt: string;
  status: AgreementStatus;
  statusRaw: ContractStatusRaw;
  transferStatus: TransferStatus;
  licenseCount: number;
  comment: string;
  fileName: string;
  fileSize: number | null;
}

export interface LicenseCatalogItem extends CatalogItemBase {
  type: 'agreements';
  kind: 'licenses';
  licenseNumber: string;
  universityId: string;
  universityName: string;
  productId: string;
  productName: string;
  vendorName: string;
  contractId: string;
  contractNumber: string;
  programId: string;
  programName: string;
  directionId: string;
  directionName: string;
  signedAt: string;
  expiresAt: string;
  status: AgreementStatus;
  transferStatus: TransferStatus;
  comment: string;
}

export type AgreementCatalogItem = ContractCatalogItem | LicenseCatalogItem;

export type CatalogItem =
  | UniversityCatalogItem
  | ProductCatalogItem
  | DirectionCatalogItem
  | ProgramCatalogItem
  | VendorCatalogItem
  | ResponsibleCatalogItem
  | AgreementCatalogItem;

export type CatalogInput =
  | { type: 'universities'; name: string; city: string }
  | { type: 'products'; name: string; vendorId: string; programId: string; version: string }
  | { type: 'directions'; name: string; code: string }
  | { type: 'programs'; name: string; directionId: string; description: string }
  | { type: 'vendors'; name: string; contacts: Array<Pick<CatalogContact, 'fullName' | 'email' | 'phone' | 'communicationMethod'>> }
  | { type: 'responsibles'; name: string; email: string; phone: string; role: string; universityIds: string[] }
  | {
      type: 'agreements';
      kind: 'contracts';
      universityId: string;
      productId: string;
      contractNumber: string;
      signedAt: string;
      expiresAt: string;
      statusRaw: ContractStatusRaw;
      transferStatus: TransferStatus;
      comment: string;
    }
  | {
      type: 'agreements';
      kind: 'licenses';
      universityId: string;
      productId: string;
      licenseNumber: string;
      contractId: string;
      programId: string;
      directionId: string;
      signedAt: string;
      expiresAt: string;
      transferStatus: TransferStatus;
      comment: string;
    };

export interface CatalogListQuery {
  type: CatalogType;
  search: string;
  page: number;
  pageSize: number;
  /** Sub-resource inside the combined agreements tab. */
  agreementKind?: AgreementKind;
  /** Supported by both contracts and licenses list endpoints. */
  universityId?: string;
  status?: AgreementStatus | '';
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
  /** Contracts feed the license form's "Договор" select. */
  contracts: CatalogReferenceOption[];
}

export const catalogDefinitions: ReadonlyArray<{ id: CatalogType; label: string; singular: string; searchPlaceholder: string }> = [
  { id: 'universities', label: 'Вузы', singular: 'ВУЗ', searchPlaceholder: 'Название или город' },
  { id: 'directions', label: 'ИТ-направления', singular: 'ИТ-направление', searchPlaceholder: 'Название или код направления' },
  { id: 'programs', label: 'ИТ-программы', singular: 'ИТ-программу', searchPlaceholder: 'Название программы' },
  { id: 'vendors', label: 'Вендоры', singular: 'вендора', searchPlaceholder: 'Название вендора' },
  { id: 'products', label: 'ИТ-продукты', singular: 'ИТ-продукт', searchPlaceholder: 'Название продукта' },
  { id: 'agreements', label: 'Договоры и лицензии', singular: 'договор или лицензию', searchPlaceholder: 'Номер договора или лицензии' },
  { id: 'responsibles', label: 'Ответственные', singular: 'ответственного', searchPlaceholder: 'ФИО или email' },
] as const;

export const catalogQueryKeys = {
  all: queryKeys.catalogs.all,
  family: queryKeys.catalogs.family,
  list: queryKeys.catalogs.list,
  detail: queryKeys.catalogs.detail,
  references: queryKeys.catalogs.references,
};

export const CATALOG_API_CAPABILITIES = {
  /** Every catalog entity is hard-deletable; the backend answers 409 when still referenced. */
  hardDelete: true,
} as const;

export function canMutateCatalog(user: AuthUser | null | undefined): boolean {
  return hasPermission(user, 'catalog.manage');
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

export async function getCatalogItem(type: CatalogType, id: string, signal?: AbortSignal, kind?: AgreementKind): Promise<CatalogItem> {
  return fromDataSource({ domain: 'catalogs', signal, mock: () => mockGetCatalogItem(type, id), real: () => realGetCatalogItem(type, id, signal, kind) });
}

export async function getCatalogReferenceData(signal?: AbortSignal): Promise<CatalogReferenceData> {
  return fromDataSource({ domain: 'catalogs', signal, mock: mockGetCatalogReferenceData, real: () => realGetCatalogReferenceData(signal) });
}

export async function createCatalogItem(input: CatalogInput): Promise<CatalogItem> {
  return fromDataSource({ domain: 'catalogs', mock: () => mockCreateCatalogItem(input), real: () => realCreateCatalogItem(input) });
}

export async function updateCatalogItem(id: string, input: CatalogInput): Promise<CatalogItem> {
  return fromDataSource({ domain: 'catalogs', mock: () => mockUpdateCatalogItem(id, input), real: () => realUpdateCatalogItem(id, input) });
}

export async function uploadContractFile(id: string, file: File): Promise<void> {
  const body = new FormData();
  body.append('file', file, file.name);
  const result = await apiUploadFormData(`/api/v1/contracts/${encodeURIComponent(id)}/file`, body);
  if (!result.ok) throw new ApiRequestError(result.status, result.body, result.error);
}

export async function downloadContractFile(id: string): Promise<Blob> {
  const result = await apiDownload(`/api/v1/contracts/${encodeURIComponent(id)}/file`);
  if (!result.ok) throw new ApiRequestError(result.status, result.body, result.error);
  return result.data;
}

export async function deleteContractFile(id: string): Promise<void> {
  const result = await apiFetch(`/api/v1/contracts/${encodeURIComponent(id)}/file`, { method: 'DELETE' });
  if (!result.ok) throw new ApiRequestError(result.status, result.body, result.error);
}

export async function deleteCatalogItem(type: CatalogType, id: string, kind?: AgreementKind): Promise<void> {
  if (!CATALOG_API_CAPABILITIES.hardDelete) {
    throw new ApiRequestError(501, { code: 'CATALOG_DELETE_UNAVAILABLE' }, 'Backend не поддерживает удаление записей каталога.');
  }
  return fromDataSource({ domain: 'catalogs', mock: async () => { await mockDeleteCatalogItem(type, id); }, real: () => realDeleteCatalogItem(type, id, kind) });
}

/** Human-readable reason why an entity cannot be removed while it is still referenced. */
export const catalogDeleteBlockers: Readonly<Record<CatalogType, string>> = {
  universities: 'Нельзя удалить ВУЗ, на который ссылаются лицензии, программы или продукты.',
  directions: 'Нельзя удалить направление, пока у него есть ИТ-программы.',
  programs: 'Нельзя удалить программу, пока на неё ссылаются продукты или ВУЗы.',
  vendors: 'Нельзя удалить вендора, пока у него есть продукты.',
  products: 'Нельзя удалить продукт, пока по нему оформлены лицензии или назначения ВУЗам.',
  agreements: 'Нельзя удалить договор, пока на него ссылаются лицензии.',
  responsibles: 'Нельзя удалить ответственного, пока он назначен хотя бы одному ВУЗу.',
};

/** Per-sub-tab hint inside the combined agreements tab. */
export const agreementDeleteBlockers: Readonly<Record<AgreementKind, string>> = {
  contracts: 'Нельзя удалить договор, пока на него ссылаются лицензии.',
  licenses: 'Удаление лицензии необратимо: история передачи прав будет потеряна.',
};

/** Derived status -> Russian label for the agreements table. */
export const agreementStatusLabels: Readonly<Record<string, string>> = {
  draft: 'Черновик',
  signed: 'Подписан',
  active: 'Действует',
  expires_soon: 'Истекает скоро',
  expired: 'Истёк',
  terminated: 'Расторгнут',
};

export const transferStatusLabels: Readonly<Record<string, string>> = {
  pending: 'Ожидает',
  transferred: 'Передан',
  accepted: 'Принят',
  rejected: 'Отклонён',
};

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
  if (type === 'programs') keys.push(queryKeys.universities.programsAll, queryKeys.universities.passports);
  if (type === 'directions') keys.push(queryKeys.universities.programsAll, queryKeys.universities.passports);
  if (type === 'responsibles') keys.push(queryKeys.users.responsibleCandidates, queryKeys.universities.responsiblesAll, queryKeys.universities.passports);
  return keys;
}
