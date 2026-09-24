export interface MockResponsibleAssignment {
  responsibleId: string;
  reason: string;
  assignedAt: string;
}

const assignments = new Map<string, MockResponsibleAssignment>();

export function getMockResponsibleAssignment(universityId: string): MockResponsibleAssignment | undefined {
  const current = assignments.get(universityId);
  if (current) return current;
  if (typeof window === 'undefined') return undefined;
  try {
    const raw = window.sessionStorage.getItem(`responsible-assignment:${universityId}`);
    if (!raw) return undefined;
    const stored: unknown = JSON.parse(raw);
    if (!stored || typeof stored !== 'object' || !('responsibleId' in stored) || typeof stored.responsibleId !== 'string') return undefined;
    const assignment = stored as MockResponsibleAssignment;
    assignments.set(universityId, assignment);
    return assignment;
  } catch { return undefined; }
}

export function setMockResponsibleAssignment(universityId: string, assignment: MockResponsibleAssignment): void {
  assignments.set(universityId, assignment);
  if (typeof window !== 'undefined') {
    try { window.sessionStorage.setItem(`responsible-assignment:${universityId}`, JSON.stringify(assignment)); } catch { /* In-memory mock still works when storage is unavailable. */ }
  }
}
