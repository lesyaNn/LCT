import { NotesPage } from '@/widgets/notes/notes-page';

export default async function NotesRoute({ searchParams }: { searchParams: Promise<{ note?: string }> }) {
  return <NotesPage requestedId={(await searchParams).note} />;
}
