import type { ButtonHTMLAttributes, ReactNode } from 'react';
import type { IconName } from '@/shared/types/navigation';
import { Icon } from './icon';
import styles from './icon-button.module.css';

type BuiltInIcon = IconName | 'menu' | 'chevron-down' | 'chevron-right' | 'bell' | 'close' | 'logout' | 'user' | 'settings';

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: BuiltInIcon | ReactNode;
  label: string;
  size?: number;
  intent?: 'default' | 'danger';
}

export function IconButton({ icon, label, size = 20, intent = 'default', className = '', ...props }: IconButtonProps) {
  return <button className={`${styles.button} ${intent === 'danger' ? styles.danger : ''} ${className}`} aria-label={label} title={props.title ?? label} type="button" {...props}>{typeof icon === 'string' ? <Icon name={icon as BuiltInIcon} size={size} /> : icon}</button>;
}
