'use client';

import { createContext, useContext, type ReactNode } from 'react';

export type NoteInsertion = { key: number; title: string; href: string; kind: string };
type NotesLauncher = { open: () => void; close: () => void; openWithLink: (link: Omit<NoteInsertion, 'key'>) => void };
const NotesLauncherContext = createContext<NotesLauncher | null>(null);

export function NotesLauncherProvider({ value, children }: { value: NotesLauncher; children: ReactNode }) {
  return <NotesLauncherContext.Provider value={value}>{children}</NotesLauncherContext.Provider>;
}

export function useNotesLauncher() {
  return useContext(NotesLauncherContext);
}
