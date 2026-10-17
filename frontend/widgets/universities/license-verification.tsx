'use client';

import Image from 'next/image';
import { useQuery } from '@tanstack/react-query';
import { verifyLicense } from '@/shared/lib/license-passports';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './license-verification.module.css';

export function LicenseVerificationPage({ licenseId }: { licenseId: string }) {
  const validId = /^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(licenseId);
  const query = useQuery({
    queryKey: ['public-license-verification', licenseId],
    queryFn: ({ signal }) => verifyLicense(licenseId, signal),
    enabled: validId, retry: false, staleTime: 0, gcTime: 0,
    refetchOnWindowFocus: 'always',
  });
  // Never show an old confirmation while a refresh is pending or has failed.
  const data = !query.isFetching && !query.isError ? query.data : undefined;
  return <main className={styles.page}><article className={styles.card}>
    <Image src="/brand/rostelecom-horizontal.svg" alt="Ростелеком · ИТ Школа" width={230} height={60} priority className={styles.logo} />
    <p className={styles.eyebrow}>ПАСПОРТ ЛИЦЕНЗИИ</p>
    <h1>Проверка подлинности</h1>
    {!validId ? <p role="alert">Некорректная ссылка проверки. Проверьте QR-код документа.</p>
      : query.isFetching ? <p role="status">Проверяем текущие сведения…</p>
      : query.isError ? <div role="alert"><h2>Не удалось проверить лицензию</h2><p>Нет ответа от сервера. Попробуйте ещё раз.</p></div>
      : data ? <>
        <StatusBadge intent={data.status === 'confirmed' ? 'success' : data.status === 'expired' ? 'warning' : 'danger'}>{data.status_label}</StatusBadge>
        <p>{data.reason}</p>
        {data.university_name ? <dl className={styles.facts}>
          <div><dt>Получатель</dt><dd>{data.university_name}</dd></div>
          <div><dt>Программное обеспечение</dt><dd>{data.product_name ?? 'Не указано'}</dd></div>
          <div><dt>Номер лицензии</dt><dd>{data.license_number ?? 'Не указан'}</dd></div>
          <div><dt>Номер договора</dt><dd>{data.contract_number ?? 'Не указан'}</dd></div>
          <div><dt>Срок действия лицензии</dt><dd>{data.signed_at ? formatDateRu(data.signed_at) : 'Не указан'} — {data.expires_at ? formatDateRu(data.expires_at) : 'Не указан'}</dd></div>
        </dl> : null}
        <p className={styles.checked}>Проверено: {formatDateTimeRu(data.checked_at)}</p>
      </> : null}
    {validId ? <Button type="button" loading={query.isFetching} disabled={query.isFetching} onClick={() => void query.refetch()}>Проверить снова</Button> : null}
    <footer>Проверка отражает текущие сведения CRM. QR-код и паспорт лицензии не заменяют договор и электронную подпись.</footer>
  </article></main>;
}
