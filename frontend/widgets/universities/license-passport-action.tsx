'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { downloadLicensePassport } from '@/shared/lib/license-passports';
import type { UniversityLicenseRow } from '@/shared/lib/universities-repository';
import { Button, ButtonAnchor } from '@/shared/ui/rtk/button';
import { Modal } from '@/shared/ui/rtk/modal';
import styles from './license-passport.module.css';

export function LicensePassportAction({ universityId, license }: { universityId: string; license: UniversityLicenseRow }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const errorId = useId();
  useEffect(() => () => { request.current?.abort(); }, []);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  if (isMockDataSourceFor('passport') || !hasPermission(user, 'university.read')) return null;

  const missing = [
    !license.product?.trim() && 'наименование ПО',
    !license.licenseNumber?.trim() && 'номер лицензии',
    !license.signedAt && 'дата начала действия',
    !license.expiresAt && 'дата окончания действия',
    (!license.contract?.trim() || license.contract === '—') && 'связанный договор',
  ].filter(Boolean);

  async function generate() {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError(null);
    setUrl(null);
    setPreview(false);
    try {
      const blob = await downloadLicensePassport(universityId, license.id, controller.signal);
      if (!controller.signal.aborted) setUrl(URL.createObjectURL(blob));
    } catch (cause) {
      if (!controller.signal.aborted) {
        const normalized = normalizeApiError(cause);
        const fields = normalized.details.missing_fields;
        setError(Array.isArray(fields) && fields.every((field) => typeof field === 'string')
          ? `Заполните или исправьте: ${fields.join('; ')}.`
          : normalized.message);
      }
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return <div className={styles.action}>
    <Button type="button" size="s" variant="secondary" loading={loading} disabled={loading || missing.length > 0}
      aria-describedby={missing.length || error ? errorId : undefined} onClick={() => void generate()}>
      {loading ? 'Формирование…' : url ? 'Сформировать заново' : 'Сформировать паспорт лицензии'}
    </Button>
    {missing.length ? <p id={errorId} className={styles.hint}>Заполните: {missing.join(', ')}.</p> : null}
    {error ? <p id={errorId} className={styles.error} role="alert">{error}</p> : null}
    {url ? <><p className={styles.hint} role="status">Паспорт готов. При изменении данных сформируйте его заново.</p><div className={styles.buttons}>
      <Button type="button" size="s" variant="ghost" onClick={() => setPreview(true)}>Открыть PDF</Button>
      <ButtonAnchor href={url} download={`license-passport-${license.id}.pdf`} size="s">Скачать PDF</ButtonAnchor>
    </div></> : null}
    {preview && url ? <Modal title="Паспорт лицензии" size="l" onClose={() => setPreview(false)}>
      <div className={styles.preview}>
        <iframe title={`Паспорт лицензии ${license.licenseNumber}`} src={url} />
        <p className={styles.hint}>Если браузер не показывает PDF, скачайте документ для просмотра и печати.</p>
        <ButtonAnchor href={url} download={`license-passport-${license.id}.pdf`}>Скачать PDF</ButtonAnchor>
      </div>
    </Modal> : null}
  </div>;
}
