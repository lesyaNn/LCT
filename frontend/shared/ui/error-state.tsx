'use client';

import type { ReactNode } from 'react';
import { StateIllustration } from './state-illustration';
import { StateActions } from './state-actions';
import type { StateAction } from './state-action';
import { StateView, type StatePresentation } from './state-view';

interface ErrorStateProps {
  title: string;
  description?: string;
  presentation?: StatePresentation;
  illustration?: ReactNode;
  icon?: ReactNode;
  onRetry?: () => void | Promise<void>;
  retryLabel?: string;
  secondaryAction?: StateAction;
  headingLevel?: 1 | 2 | 3;
  className?: string;
}

export function ErrorState({
  title,
  description,
  presentation = 'compact',
  illustration,
  icon,
  onRetry,
  retryLabel = 'Повторить',
  secondaryAction,
  headingLevel,
  className,
}: ErrorStateProps) {
  const primaryAction: StateAction | undefined = onRetry ? { label: retryLabel, onClick: onRetry } : undefined;
  const visual = illustration ?? (presentation === 'large' ? <StateIllustration kind="error" /> : undefined);
  return (
    <StateView
      actions={primaryAction || secondaryAction ? <StateActions primary={primaryAction} secondary={secondaryAction} /> : undefined}
      ariaLive="assertive"
      className={className}
      description={description}
      headingLevel={headingLevel ?? (presentation === 'large' ? 1 : 2)}
      icon={icon}
      presentation={presentation}
      role="alert"
      title={title}
      visual={visual}
    />
  );
}
