import { EntityDetailPlaceholder } from '@/shared/ui/entity-detail-placeholder';

export default async function WorkflowDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return <EntityDetailPlaceholder eyebrow="Workflow" title="Взаимодействие" description="Детали workflow будут подключены в следующем функциональном модуле." routeId={id} />;
}
