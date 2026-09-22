import { Suspense } from 'react';
import { PageSkeleton } from '@/shared/ui/page-skeleton';
import { UniversitiesList } from '@/widgets/universities/universities-list';

export default function UniversitiesPage() {
  return (
    <Suspense fallback={<PageSkeleton cardCount={6} />}>
      <UniversitiesList />
    </Suspense>
  );
}
