import type { Metadata } from 'next';
import { LicenseVerificationPage } from '@/widgets/universities/license-verification';

export const metadata: Metadata = {
  title: 'Проверка лицензии · ИТ Школа Ростелеком',
  robots: { index: false, follow: false },
  referrer: 'no-referrer',
};

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <LicenseVerificationPage licenseId={id} />;
}
