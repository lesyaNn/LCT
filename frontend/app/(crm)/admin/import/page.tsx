import { PageIntro } from '@/shared/ui/page-intro';
import { ImportPage } from '@/widgets/admin/import-page';

export default function CatalogImportRoute() {
  return <><PageIntro title="Импорт каталогов" description="Загрузите XLSX, выберите один лист или импортируйте весь файл сразу — с проверкой перед записью." /><ImportPage /></>;
}
