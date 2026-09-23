import Link from 'next/link';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './button.module.css';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 's' | 'm' | 'l';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

interface ButtonLinkProps {
  href: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: ReactNode;
}

export function Button({ variant = 'secondary', size = 'm', className = '', children, ...props }: ButtonProps) {
  return <button className={`${styles.button} ${styles[variant]} ${styles[size]} ${className}`} {...props}>{children}</button>;
}

export function ButtonLink({ href, variant = 'secondary', size = 'm', className = '', children }: ButtonLinkProps) {
  return <Link className={`${styles.button} ${styles[variant]} ${styles[size]} ${className}`} href={href}>{children}</Link>;
}
