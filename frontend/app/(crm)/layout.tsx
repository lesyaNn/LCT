import { AuthProvider } from '@/shared/auth/AuthProvider';
import { AppShell } from '@/widgets/app-shell/AppShell';

export default function CrmLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AuthProvider><AppShell>{children}</AppShell></AuthProvider>;
}
