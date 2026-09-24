import { PageIntro } from '@/shared/ui/page-intro';
import { ImportPage } from '@/widgets/admin/import-page';

export default function CatalogImportRoute() {
  return <><PageIntro eyebrow="Администрирование" title="Импорт каталогов" description="Загрузите XLSX, сопоставьте колонки и безопасно проверьте изменения перед импортом." /><ImportPage /></>;
}
