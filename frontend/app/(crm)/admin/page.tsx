'use client';

import Link from 'next/link';
import { useAuth } from '@/shared/auth/AuthProvider';
import { getVisibleNavigationItems } from '@/shared/config/navigation';
import { PageIntro } from '@/shared/ui/page-intro';
import styles from '../section-page.module.css';

export default function AdminPage() {
  const { user } = useAuth();
  const sections = user ? getVisibleNavigationItems(user).filter((item) => item.href.startsWith('/admin/')) : [];

  return <div className={styles.page}>
    <PageIntro title="Администрирование" description="Выберите раздел в боковом меню." />
    <section className={styles.adminOverview} aria-label="Разделы администрирования">
      {sections.map((item) => <Link className={styles.adminLink} href={item.href} key={item.href}><span>{item.label}</span><span aria-hidden="true">→</span></Link>)}
    </section>
  </div>;
}
