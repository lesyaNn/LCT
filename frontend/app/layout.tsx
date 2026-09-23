import type { Metadata } from 'next';
import { AuthProvider } from '@/shared/auth/AuthProvider';
import { QueryProvider } from '@/shared/providers/query-provider';
import '../styles/globals.css';

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000'),
  title: 'CRM ИТ-Школа Ростелеком',
  description: 'CRM для взаимодействия с вузами и контроля подготовки ИТ-кадров.',
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/favicon-16.svg', sizes: '16x16', type: 'image/svg+xml' },
      { url: '/favicon-32.svg', sizes: '32x32', type: 'image/svg+xml' },
    ],
    apple: [{ url: '/apple-touch-icon.svg', sizes: '180x180', type: 'image/svg+xml' }],
  },
  openGraph: {
    title: 'CRM ИТ-Школа Ростелеком',
    description: 'Взаимодействие с вузами и контроль подготовки ИТ-кадров.',
    type: 'website',
    locale: 'ru_RU',
    siteName: 'CRM ИТ-Школа Ростелеком',
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" className="Theme_root_rtk_purple_light">
      <body><QueryProvider><AuthProvider>{children}</AuthProvider></QueryProvider></body>
    </html>
  );
}
