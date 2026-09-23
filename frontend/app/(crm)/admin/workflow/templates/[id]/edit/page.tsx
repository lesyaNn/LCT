import { WorkflowTemplateEditor } from '@/widgets/admin/workflow-template-editor';

export default async function WorkflowTemplateEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WorkflowTemplateEditor templateId={id} />;
}
