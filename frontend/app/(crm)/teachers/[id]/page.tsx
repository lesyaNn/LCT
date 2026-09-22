import { EntityDetailPlaceholder } from '@/shared/ui/entity-detail-placeholder';

export default async function TeacherDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return <EntityDetailPlaceholder eyebrow="Преподаватели" title="Преподаватель" description="Карточка преподавателя будет подключена в следующем функциональном модуле." routeId={id} />;
}
