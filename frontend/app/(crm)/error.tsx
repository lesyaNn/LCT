'use client';

import { RouteErrorState } from '@/shared/ui/route-error-state';

export default function ErrorPage({ reset }: Readonly<{
  error: Error & { digest?: string };
  reset: () => void;
}>) {
  return <RouteErrorState onRetry={reset} />;
}
