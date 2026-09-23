'use client';

import { useRouter } from 'next/navigation';
import { StateIllustration, type StateIllustrationKind } from './state-illustration';
import { StateActions } from './state-actions';
import type { StateAction } from './state-action';
import { StateView } from './state-view';

interface StatusPageProps {
  code: '403' | '404' | '500';
  title: string;
  description: string;
  onRetry?: () => void | Promise<void>;
  showBack?: boolean;
  withinAppShell?: boolean;
}

export function StatusPage({ code, title, description, onRetry, showBack = true, withinAppShell = false }: StatusPageProps) {
  const router = useRouter();
  const primaryAction: StateAction = code === '500' && onRetry
    ? { label: 'Повторить', onClick: onRetry }
    : { label: 'На главную', href: '/dashboard' };
  const secondaryAction: StateAction | undefined = code === '500'
    ? { label: 'На главную', href: '/dashboard' }
    : showBack
      ? { label: 'Назад', onClick: () => router.back() }
      : undefined;

  const content = <StateView actions={<StateActions primary={primaryAction} secondary={secondaryAction} />} ariaLive={code === '500' ? 'assertive' : 'off'} description={description} eyebrow={code} eyebrowStyle="code" headingLevel={1} presentation="large" role={code === '500' ? 'alert' : undefined} title={title} visual={<StateIllustration kind={code as StateIllustrationKind} />} />;
  return withinAppShell ? content : <main>{content}</main>;
}
