import { WorkflowView } from '@/widgets/universities/university-workflow';

export default async function WorkflowDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return <WorkflowView instanceId={id} mode="page" />;
}
