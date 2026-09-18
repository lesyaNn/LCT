/** Shared domain DTOs (P1: types live here, not inside components). */
export type Me = {
  id: string;
  username: string | null;
  email: string | null;
  name: string | null;
  roles: string[];
  permissions: string[];
};

export type CatalogRow = {
  university: string | null;
  vendor: string | null;
  product: string | null;
  contract_number: string | null;
  signed_at: string | null;
  expires_at: string | null;
  transfer_status: string | null;
  manager: string | null;
  responsibles: string[];
  comment: string | null;
  direction: string | null;
};

export type CatalogDirection = { code: string; name: string; programs: number };

export type CatalogOverview = {
  total_universities: number;
  total_licenses: number;
  page?: number;
  page_size?: number;
  rows: CatalogRow[];
  directions: CatalogDirection[];
};
