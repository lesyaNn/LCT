import { StatusPage } from './status-page';

export function NotFoundState() {
  return <StatusPage code="404" title="Страница не найдена" description="Возможно, адрес изменился или такой страницы больше нет." />;
}
