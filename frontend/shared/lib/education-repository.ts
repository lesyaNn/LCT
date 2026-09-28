import { ApiRequestError } from './api-errors';
import { apiFetch } from './api-client';
import type { WorkflowPage } from './universities-repository';

function unwrap<T>(result: Awaited<ReturnType<typeof apiFetch<T>>>): T {
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить данные обучения.', result.error);
}

export type LearnerStatus = 'active' | 'graduated' | 'expelled' | 'academic_leave';
export interface LearnerRecord {
  id: string; external_id: string; university_id: string; program_id: string;
  full_name: string; group_name: string | null; status: LearnerStatus;
  started_at: string; finished_at: string | null;
  source: 'manual' | 'lms' | 'mock_lms'; progress: number | null; synced_at: string | null;
}
export interface LearnerSummary {
  university_id: string; learners: number; active_learners: number; flows: number;
  programs: { program_id: string; program_name: string; learners: number; active_learners: number; flows: number; lms_learners: number }[];
}
export type LearnerCreate = Pick<LearnerRecord, 'external_id' | 'program_id' | 'full_name' | 'group_name' | 'status' | 'started_at' | 'finished_at'>;

export const educationKeys = {
  learners: (universityId: string, page: number, programId: string, status: string) => ['education', universityId, 'learners', page, programId, status] as const,
  summary: (universityId: string) => ['education', universityId, 'summary'] as const,
  teachers: (universityId: string, page: number) => ['education', universityId, 'teachers', page] as const,
  family: (universityId: string) => ['education', universityId] as const,
};

export async function listLearners(universityId: string, page: number, programId = '', status = ''): Promise<WorkflowPage<LearnerRecord>> {
  const params = new URLSearchParams({ page: String(page), page_size: '20' });
  if (programId) params.set('program_id', programId);
  if (status) params.set('status', status);
  return unwrap(await apiFetch<WorkflowPage<LearnerRecord>>(`/api/v1/universities/${universityId}/students?${params}`));
}
export async function learnerSummary(universityId: string): Promise<LearnerSummary> {
  return unwrap(await apiFetch<LearnerSummary>(`/api/v1/universities/${universityId}/students/summary`));
}
export async function createLearner(universityId: string, input: LearnerCreate): Promise<LearnerRecord> {
  return unwrap(await apiFetch<LearnerRecord>(`/api/v1/universities/${universityId}/students`, { method: 'POST', body: input }));
}
export async function updateLearner(id: string, input: Partial<LearnerCreate>): Promise<LearnerRecord> {
  return unwrap(await apiFetch<LearnerRecord>(`/api/v1/students/${id}`, { method: 'PATCH', body: input }));
}
export async function deleteLearner(id: string): Promise<void> {
  return unwrap(await apiFetch<void>(`/api/v1/students/${id}`, { method: 'DELETE' }));
}
export async function syncDemoLms(universityId: string): Promise<{ processed: number; unresolved: number; mode: string }> {
  return unwrap(await apiFetch<{ processed: number; unresolved: number; mode: string }>('/api/v1/integrations/sync', { method: 'POST', body: { university_id: universityId, source: 'lms' } }));
}
export async function integrationCapabilities(): Promise<{ demo_lms_enabled: boolean; demo_website_enabled: boolean; live_provider_configured: boolean }> {
  return unwrap(await apiFetch('/api/v1/integrations/capabilities'));
}

export interface QualificationRecord { id: string; qualification_name: string; obtained_at: string; expires_at: string | null; document_ref: string | null }
export interface CertificateRecord { id: string; certificate_name: string; issued_by: string; issued_at: string; expires_at: string | null; is_mandatory: boolean; program_id: string | null; document_ref: string | null }
export interface TeacherProgramRecord { id: string; program_id: string; can_teach: boolean; assigned_at: string }
export interface TeacherRecord {
  id: string; university_id: string; full_name: string; email: string; phone: string | null; position: string;
  qualifications: QualificationRecord[]; certificates: CertificateRecord[]; teacher_programs: TeacherProgramRecord[];
}
export type TeacherCreate = Pick<TeacherRecord, 'full_name' | 'email' | 'phone' | 'position'>;
export async function listTeachers(universityId: string, page: number): Promise<WorkflowPage<TeacherRecord>> {
  return unwrap(await apiFetch<WorkflowPage<TeacherRecord>>(`/api/v1/universities/${universityId}/teachers?page=${page}&page_size=20`));
}
export async function createTeacher(universityId: string, input: TeacherCreate): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/universities/${universityId}/teachers`, { method: 'POST', body: input }));
}
export async function updateTeacher(id: string, input: Partial<TeacherCreate>): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/teachers/${id}`, { method: 'PATCH', body: input }));
}
export async function deleteTeacher(id: string): Promise<void> {
  return unwrap(await apiFetch<void>(`/api/v1/teachers/${id}`, { method: 'DELETE' }));
}
export async function removeTeacherChild(id: string, kind: 'qualifications' | 'certificates' | 'programs', childId: string): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/teachers/${id}/${kind}/${childId}`, { method: 'DELETE' }));
}
export async function addQualification(id: string, input: Omit<QualificationRecord, 'id'>): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/teachers/${id}/qualifications`, { method: 'POST', body: input }));
}
export async function addCertificate(id: string, input: Omit<CertificateRecord, 'id'>): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/teachers/${id}/certificates`, { method: 'POST', body: input }));
}
export async function addTeacherProgram(id: string, input: Omit<TeacherProgramRecord, 'id'>): Promise<TeacherRecord> {
  return unwrap(await apiFetch<TeacherRecord>(`/api/v1/teachers/${id}/programs`, { method: 'POST', body: input }));
}
