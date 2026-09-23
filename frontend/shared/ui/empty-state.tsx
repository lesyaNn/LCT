'use client';

import type { ReactNode } from 'react';
import { StateIllustration } from './state-illustration';
import { StateActions } from './state-actions';
import type { StateAction } from './state-action';
import { StateView, type StatePresentation } from './state-view';

interface EmptyStateProps {
  title: string;
  description?: string;
  presentation?: StatePresentation;
  illustration?: ReactNode;
  icon?: ReactNode;
  primaryAction?: StateAction;
  secondaryAction?: StateAction;
  headingLevel?: 1 | 2 | 3;
  announce?: boolean;
  className?: string;
}

export function EmptyState({
  title,
  description,
  presentation = 'compact',
  illustration,
  icon,
  primaryAction,
  secondaryAction,
  headingLevel,
  announce = true,
  className,
}: EmptyStateProps) {
  const visual = illustration ?? (presentation === 'large' ? <StateIllustration kind="empty" /> : undefined);
  return (
    <StateView
      actions={primaryAction || secondaryAction ? <StateActions primary={primaryAction} secondary={secondaryAction} /> : undefined}
      ariaLive={announce ? 'polite' : 'off'}
      className={className}
      description={description}
      headingLevel={headingLevel ?? (presentation === 'large' ? 1 : 2)}
      icon={icon}
      presentation={presentation}
      role={announce ? 'status' : undefined}
      title={title}
      visual={visual}
    />
  );
}
