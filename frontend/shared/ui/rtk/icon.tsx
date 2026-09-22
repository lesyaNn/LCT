import type { IconName } from '@/shared/types/navigation';

interface IconProps {
  name: IconName | 'menu' | 'chevron-down' | 'chevron-right' | 'bell' | 'close' | 'logout' | 'user' | 'settings';
  size?: number;
}

export function Icon({ name, size = 20 }: IconProps) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', 'aria-hidden': true };

  const paths: Record<IconProps['name'], React.ReactNode> = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    university: <><path d="m3 9 9-5 9 5-9 5-9-5Z" /><path d="M6 11v5c2.9 2.3 9.1 2.3 12 0v-5M21 9v7" /></>,
    teacher: <><circle cx="9" cy="8" r="3" /><path d="M3.5 20c.4-3.3 2.2-5 5.5-5s5.1 1.7 5.5 5M16 11a3 3 0 1 0 0-6M16 15c2.8 0 4.3 1.7 4.5 5" /></>,
    workflow: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8.5 6h7M7.5 8l3 7.5M16.5 8l-3 7.5" /></>,
    report: <><path d="M5 20V10M12 20V4M19 20v-7" /><path d="M3 20h18" /></>,
    audit: <><path d="M12 3 5 6v5c0 4.4 2.8 8.3 7 10 4.2-1.7 7-5.6 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
    admin: <><circle cx="12" cy="8" r="3" /><path d="M5 21c.5-3.7 2.8-5.5 7-5.5s6.5 1.8 7 5.5M19 8h2M20 5.5l1.5-1.5M20 10.5l1.5 1.5" /></>,
    docs: <><path d="M6 3h9l3 3v15H6V3Z" /><path d="M15 3v4h4M9 12h6M9 16h6" /></>,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    'chevron-down': <path d="m6 9 6 6 6-6" />,
    'chevron-right': <path d="m9 6 6 6-6 6" />,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    logout: <><path d="M14 8V5H5v14h9v-3M11 12h10M18 9l3 3-3 3" /></>,
    user: <><circle cx="12" cy="8" r="3" /><path d="M5 21c.5-3.7 2.8-5.5 7-5.5s6.5 1.8 7 5.5" /></>,
    settings: <><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" /><circle cx="12" cy="12" r="4" /></>,
  };

  return <svg {...common} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}
