import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './button.module.css';

type ButtonVariant = 'primary' | 'secondary' | 'ghost';
type ButtonSize = 's' | 'm' | 'l';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

export function Button({ variant = 'secondary', size = 'm', className = '', children, ...props }: ButtonProps) {
  return <button className={`${styles.button} ${styles[variant]} ${styles[size]} ${className}`} {...props}>{children}</button>;
}
