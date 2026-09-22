import type { ButtonHTMLAttributes } from 'react';
import type { IconName } from '@/shared/types/navigation';
import { Icon } from './icon';
import styles from './icon-button.module.css';

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName | 'menu' | 'chevron-down' | 'chevron-right' | 'bell' | 'close' | 'logout' | 'user' | 'settings';
  label: string;
  size?: number;
}

export function IconButton({ icon, label, size = 20, className = '', ...props }: IconButtonProps) {
  return <button className={`${styles.button} ${className}`} aria-label={label} type="button" {...props}><Icon name={icon} size={size} /></button>;
}
