import { EntityDetailPlaceholder } from '@/shared/ui/entity-detail-placeholder';

export default async function UniversityDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return <EntityDetailPlaceholder eyebrow="ВУЗы" title="Университет" description="Карточка университета будет подключена в следующем функциональном модуле." routeId={id} />;
}
