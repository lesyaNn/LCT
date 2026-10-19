import { UsersPage } from '@/widgets/admin/users-page';

export default async function AdminUsersRoute({ searchParams }: { searchParams: Promise<{ user?: string }> }) {
  const id = (await searchParams).user;
  return <UsersPage key={id} initialUserId={id} />;
}
