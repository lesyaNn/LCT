import type { Metadata } from 'next';
import { AuthProvider } from '@/shared/auth/AuthProvider';
import '../styles/globals.css';

export const metadata: Metadata = {
  title: 'ИТ Школа РТК — CRM',
  description: 'CRM для управления взаимодействием с учебными заведениями.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
