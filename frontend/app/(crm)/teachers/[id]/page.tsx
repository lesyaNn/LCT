import { TeacherPassport } from '@/widgets/teachers/teacher-passport';

export default async function TeacherDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return <TeacherPassport id={id} />;
}
