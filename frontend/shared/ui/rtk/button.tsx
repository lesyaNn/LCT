import Link from 'next/link';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './button.module.css';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'orange';
type ButtonSize = 's' | 'm' | 'l';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
}

interface ButtonLinkProps {
  href: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: ReactNode;
}

export function Button({ variant = 'secondary', size = 'm', className = '', children, loading = false, ...props }: ButtonProps) {
  return <button aria-busy={loading || undefined} className={`${styles.button} ${styles[variant]} ${styles[size]} ${className}`} {...props}>{loading ? <span className={styles.spinner} aria-hidden="true" /> : null}<span className={styles.label}>{children}</span></button>;
}

export function ButtonLink({ href, variant = 'secondary', size = 'm', className = '', children }: ButtonLinkProps) {
  return <Link className={`${styles.button} ${styles[variant]} ${styles[size]} ${className}`} href={href}>{children}</Link>;
}
