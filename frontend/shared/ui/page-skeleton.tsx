import { MetricCardSkeleton, Skeleton, SkeletonGroup, TextSkeleton } from './skeleton';

export function PageSkeleton({ cardCount = 3, variant = 'default' }: { cardCount?: number; variant?: 'default' | 'dashboard' }) {
  return (
    <SkeletonGroup label="Загружаем раздел">
      <Skeleton variant="text" width="min(44%, 280px)" height={14} />
      <TextSkeleton lines={2} widths={['min(72%, 520px)', 'min(54%, 390px)']} />
      <MetricCardSkeleton count={variant === 'dashboard' ? cardCount : Math.min(cardCount, 4)} />
      {variant === 'dashboard' ? <><Skeleton height={320} /><Skeleton height={320} /></> : null}
    </SkeletonGroup>
  );
}
