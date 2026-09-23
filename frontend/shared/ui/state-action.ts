export type StateAction =
  | { label: string; href: string; onClick?: never; variant?: 'primary' | 'secondary' | 'ghost' }
  | { label: string; onClick: () => void | Promise<void>; href?: never; variant?: 'primary' | 'secondary' | 'ghost' };
