'use client';

import Image from 'next/image';
import { useCallback, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { verifyLicense } from '@/shared/lib/license-passports';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import { Button } from '@/shared/ui/rtk/button';
import { LicenseVerificationStamp } from './license-confirmation-stamp';
import styles from './license-verification.module.css';

export function LicenseVerificationPage({ licenseId }: { licenseId: string }) {
  const stampedLicense = useRef<string | null>(null);
  const claimStampAnimation = useCallback(() => {
    if (stampedLicense.current === licenseId) return false;
    stampedLicense.current = licenseId;
    return true;
  }, [licenseId]);
  const validId = /^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(licenseId);
  const query = useQuery({
    queryKey: ['public-license-verification', licenseId],
    queryFn: ({ signal }) => verifyLicense(licenseId, signal),
    enabled: validId, retry: false, staleTime: 0, gcTime: 0,
    refetchOnWindowFocus: 'always',
  });
  // Never show an old confirmation while a refresh is pending or has failed.
  const data = !query.isFetching && !query.isError ? query.data : undefined;
  const stampKind = data?.status === 'confirmed' ? 'confirmed'
    : data?.status === 'invalid' && data.university_name === null
      && data.product_name === null && data.license_number === null ? 'not-found' : null;
  return <main className={styles.page}><article className={styles.card}>
    <Image src="/brand/rostelecom-horizontal.svg" alt="Ростелеком · ИТ Школа" width={230} height={60} priority className={styles.logo} />
    <p className={styles.eyebrow}>ПАСПОРТ ЛИЦЕНЗИИ</p>
    <h1>Проверка подлинности</h1>
    {!validId ? <p role="alert">Некорректная ссылка проверки. Проверьте QR-код документа.</p>
      : query.isFetching ? <p role="status">Проверяем текущие сведения…</p>
      : query.isError ? <div role="alert"><h2>Не удалось проверить лицензию</h2><p>Нет ответа от сервера. Попробуйте ещё раз.</p></div>
      : data ? <>
        <span className={styles.statusText} role="status" aria-label={data.status_label} />
        {stampKind !== 'not-found' ? <p>{data.reason}</p> : null}
        {data.university_name || stampKind ? <section className={`${styles.facts} ${stampKind === 'not-found' ? styles.notFoundFacts : stampKind === 'confirmed' ? styles.confirmedFacts : ''}`} aria-label="Сведения о лицензии">
          {stampKind === 'not-found' ? <div className={styles.notFoundCopy}>
            <p>В реестре нет записи об этой лицензии.</p>
            <p>{data.reason}</p>
          </div> : null}
          {data.university_name ? <dl className={styles.factsList}>
          <div><dt>Получатель</dt><dd>{data.university_name}</dd></div>
          <div><dt>Программное обеспечение</dt><dd>{data.product_name ?? 'Не указано'}</dd></div>
          <div><dt>Номер лицензии</dt><dd>{data.license_number ?? 'Не указан'}</dd></div>
          <div><dt>Номер договора</dt><dd>{data.contract_number ?? 'Не указан'}</dd></div>
          <div><dt>Срок действия лицензии</dt><dd>{data.signed_at ? formatDateRu(data.signed_at) : 'Не указан'} — {data.expires_at ? formatDateRu(data.expires_at) : 'Не указан'}</dd></div>
          </dl> : null}
          {stampKind ? <LicenseVerificationStamp key={`${licenseId}-${stampKind}`} kind={stampKind} claimAnimation={claimStampAnimation} /> : null}
        </section> : null}
        <p className={styles.checked}>Проверено: {formatDateTimeRu(data.checked_at)}</p>
      </> : null}
    {validId ? <Button type="button" loading={query.isFetching} disabled={query.isFetching} onClick={() => void query.refetch()}>Проверить снова</Button> : null}
    <footer>Проверка отражает текущие сведения CRM. QR-код и паспорт лицензии не заменяют договор и электронную подпись.</footer>
  </article></main>;
}
