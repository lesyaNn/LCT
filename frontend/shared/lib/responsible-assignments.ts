export interface MockResponsibleAssignment {
  responsibleId: string;
  reason: string;
  assignedAt: string;
}

const assignments = new Map<string, MockResponsibleAssignment>();

export function getMockResponsibleAssignment(universityId: string): MockResponsibleAssignment | undefined {
  return assignments.get(universityId);
}

export function setMockResponsibleAssignment(universityId: string, assignment: MockResponsibleAssignment): void {
  assignments.set(universityId, assignment);
}
