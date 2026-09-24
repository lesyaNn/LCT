import { PageIntro } from '@/shared/ui/page-intro';
import { isImportCatalogType } from '@/shared/lib/import-repository';
import { ImportPage } from '@/widgets/admin/import-page';

export default async function CatalogImportRoute({ searchParams }: { searchParams: Promise<{ type?: string | string[] }> }) {
  const rawType = (await searchParams).type;
  const requestedType = Array.isArray(rawType) ? rawType.at(-1) : rawType;
  const initialCatalogType = isImportCatalogType(requestedType) ? requestedType : '';
  return <><PageIntro title="Импорт каталогов" description="Загрузите XLSX, сопоставьте колонки и безопасно проверьте изменения перед импортом." /><ImportPage initialCatalogType={initialCatalogType} /></>;
}
