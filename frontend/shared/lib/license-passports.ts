'use client';

import { apiDownload, apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';

export async function downloadLicensePassport(universityId: string, licenseId: string, signal?: AbortSignal) {
  const result = await apiDownload(`/api/v1/universities/${encodeURIComponent(universityId)}/licenses/${encodeURIComponent(licenseId)}/passport.pdf`, signal);
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось сформировать паспорт лицензии.');
  if (!result.data.type.includes('application/pdf')) throw new Error('Сервер вернул файл в неверном формате.');
  return result.data;
}

export interface LicenseVerification {
  status: 'confirmed' | 'invalid' | 'revoked' | 'expired';
  status_label: string;
  reason: string;
  checked_at: string;
  university_name: string | null;
  product_name: string | null;
  license_number: string | null;
  contract_number: string | null;
  signed_at: string | null;
  expires_at: string | null;
}

export async function verifyLicense(licenseId: string, signal?: AbortSignal): Promise<LicenseVerification> {
  const result = await apiFetch<LicenseVerification>(`/api/v1/public/licenses/${encodeURIComponent(licenseId)}/verification`, { anonymous: true, signal });
  if (!result.ok) throw new ApiRequestError(result.status, result.body);
  return result.data;
}
