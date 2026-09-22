import { AppShell } from '@/widgets/app-shell/AppShell';

export default function CrmLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AppShell>{children}</AppShell>;
}
