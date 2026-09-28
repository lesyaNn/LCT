import { ApiRequestError } from './api-errors';
import { apiFetch } from './api-client';
import type { WorkflowPage } from './universities-repository';

function unwrap<T>(result: Awaited<ReturnType<typeof apiFetch<T>>>): T {
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить данные обучения.', result.error);
}

export interface ProgramEducationStats {
  program_id: string;
  program_name: string;
  learners_count: number;
  applications_count: number;
  flows_count: number;
  learner_source: 'lms' | 'mock_lms' | 'manual' | null;
  learner_synced_at: string | null;
  applications_synced_at: string | null;
}

export interface UniversityEducationStats {
  university_id: string;
  learners_count: number;
  applications_count: number;
  flows_count: number;
  programs: ProgramEducationStats[];
}

export type TrainingStatus = 'not_started' | 'in_progress' | 'completed' | 'needs_review';
export interface TeacherProgram {
  id: string;
  program_id: string;
  training_status: TrainingStatus;
  qualification_status: TrainingStatus;
  last_training_at: string | null;
  next_qualification_due_at: string | null;
}
export interface TeacherRecord {
  id: string;
  university_id: string;
  full_name: string;
  teacher_programs: TeacherProgram[];
}
export interface TeacherProgramInput {
  program_id: string;
  training_status?: TrainingStatus;
  qualification_status?: TrainingStatus;
  last_training_at?: string | null;
  next_qualification_due_at?: string | null;
}

export const educationKeys = {
  family: (universityId: string) => ['education', universityId] as const,
  stats: (universityId: string) => ['education', universityId, 'stats'] as const,
  teachers: (universityId: string, page: number) => ['education', universityId, 'teachers', page] as const,
};

export async function educationStatistics(universityId: string): Promise<UniversityEducationStats> {
  return unwrap(await apiFetch<UniversityEducationStats>(`/api/v1/universities/${universityId}/education-statistics`));
}
export async function listTeachers(universityId: string, page: number): Promise<WorkflowPage<TeacherRecord>> {
  return unwrap(await apiFetch<WorkflowPage<TeacherRecord>>(`/api/v1/universities/${universityId}/teachers?page=${page}&page_size=20`));
}
export async function createTeacher(universityId: string, input: { full_name: string; program_id: string }): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/universities/${universityId}/teachers`, { method: 'POST', body: input }));
}
export async function updateTeacher(id: string, fullName: string): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/teachers/${id}`, { method: 'PATCH', body: { full_name: fullName } }));
}
export async function addTeacherProgram(id: string, input: TeacherProgramInput): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/teachers/${id}/programs`, { method: 'POST', body: input }));
}
export async function updateTeacherProgram(id: string, programId: string, input: Omit<TeacherProgramInput, 'program_id'>): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/teachers/${id}/programs/${programId}`, { method: 'PATCH', body: input }));
}
export async function integrationCapabilities(): Promise<{ demo_lms_enabled: boolean }> {
  return unwrap(await apiFetch('/api/v1/integrations/capabilities'));
}
export async function syncDemoLms(universityId: string): Promise<{ processed: number; unresolved: number }> {
  return unwrap(await apiFetch('/api/v1/integrations/sync', {
    method: 'POST', body: { university_id: universityId, source: 'lms' },
  }));
}
