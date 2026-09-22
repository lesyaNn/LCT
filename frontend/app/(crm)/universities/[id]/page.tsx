import { Suspense } from 'react';
import { PageSkeleton } from '@/shared/ui/page-skeleton';
import { UniversityPassport } from '@/widgets/universities/university-passport';

export default async function UniversityDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <Suspense fallback={<PageSkeleton cardCount={4} variant="dashboard" />}>
      <UniversityPassport id={id} />
    </Suspense>
  );
}
