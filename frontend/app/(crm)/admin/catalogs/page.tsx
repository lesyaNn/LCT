import { Suspense } from 'react';
import { CatalogsPage } from '@/widgets/admin/catalogs-page';

export default function CatalogsRoute() {
  return <Suspense fallback={<p>Загрузка каталогов…</p>}><CatalogsPage /></Suspense>;
}
