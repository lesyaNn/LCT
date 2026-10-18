'use client';

import { Suspense } from 'react';
import { useAuth } from '@/shared/auth/AuthProvider';
import { NotesWorkspace } from '@/widgets/notes/notes-workspace';

export default function NotesPage() {
  const { user } = useAuth();
  return user ? <Suspense fallback={null}><NotesWorkspace userId={user.id} /></Suspense> : null;
}
