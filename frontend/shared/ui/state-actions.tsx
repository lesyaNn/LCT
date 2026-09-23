'use client';

import { Button, ButtonLink } from '@/shared/ui/rtk/button';
import type { StateAction } from './state-action';

export function StateActions({ primary, secondary }: { primary?: StateAction; secondary?: StateAction }) {
  const renderAction = (action: StateAction, fallbackVariant: 'primary' | 'secondary') => typeof action.href === 'string'
    ? <ButtonLink href={action.href} size="m" variant={action.variant ?? fallbackVariant}>{action.label}</ButtonLink>
    : <Button type="button" size="m" variant={action.variant ?? fallbackVariant} onClick={() => void action.onClick?.()}>{action.label}</Button>;

  return <>{primary ? renderAction(primary, 'primary') : null}{secondary ? renderAction(secondary, 'secondary') : null}</>;
}
