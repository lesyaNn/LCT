import { apiFetch, apiUploadFormData } from './api-client';
import { ApiRequestError } from './api-errors';
import { getExpirationStatus } from './formatters';
import { getHealthStatus } from './health-score';
import type { ImportExecuteResponse, ImportOptions, ImportPreviewResponse } from './import-repository';
import type {
  PaginatedResult,
  ProgramStatus,
  TeacherCertificate,
  TeacherPassport,
  TeacherQualification,
  TeacherReadiness,
  UniversityDocumentRow,
  UniversityFilters,
  UniversityHealthScore,
  UniversityHistoryEvent,
  UniversityHistoryFilters,
  UniversityLicenseRow,
  UniversityListItem,
  UniversityListQuery,
  UniversityMeetingRow,
  UniversityPassport,
  UniversityProductRow,
  UniversityProgramRow,
  UniversityResponsible,
  UniversityResponsibleContact,
  UniversityStudentsSummary,
  UniversityTeacherRow,
} from './universities-repository';

type ApiPage<T> = { items: T[]; page: number; page_size: number; total: number };
type ApiUniversity = { id: string; name: string; city: string | null; created_at: string; updated_at: string };
type ApiProgram = { id: string; name: string; direction_name: string; status: ProgramStatus; launch_date: string | null; responsible_name: string | null; teachers_count: number; students_count: number };
type ApiTeacher = { id: string; full_name: string; email: string; position: string; readiness: TeacherReadiness; next_qualification_date: string | null; programs: ApiProgram[] };
type ApiLicense = { id: string; license_number: string; product_name: string; vendor_name: string; signed_at: string; expires_at: string; status: string; transfer_status: string; contract_number: string | null };
type ApiProduct = { id: string; name: string; version: string; vendor_name: string; status: string; license: ApiLicense | null };
type ApiDocument = { id: string; document_type: string; title: string; file_name: string; file_size: number; signed_at: string | null; expires_at: string | null; status: string; uploaded_by: string; created_at: string };
type ApiMeeting = { id: string; meeting_type: string; subject: string; participants: string[]; outcome: string | null; next_action: string | null; next_action_due: string | null; meeting_at: string; created_by: string };
type ApiResponsible = { id: string; full_name: string; email: string; phone: string | null; role: string };
type ApiTimeline = { id: string; type: string; title: string; description: string | null; author: string; created_at: string };
type ApiWorkflowSummary = { instance_id: string | null; template_name: string | null; current_stage: string | null; progress_percent: number; overdue_stages: number; next_due_date: string | null };
type ApiStudents = { total: number; active: number; graduated: number; by_status: Record<string, number>; by_program: Array<{ program_id: string; program_name: string; total: number; active: number; graduated: number }> };
type ApiPassport = {
  university: { id: string; name: string; city: string | null };
  programs: ApiProgram[];
  teachers: ApiTeacher[];
  students_summary: ApiStudents;
  products: ApiProduct[];
  licenses: ApiLicense[];
  documents: ApiDocument[];
  meetings: ApiMeeting[];
  responsibles: ApiResponsible[];
  workflow_summary: ApiWorkflowSummary;
  last_interactions: ApiTimeline[];
  health_score: { score: number } | null;
};

type ApiHealthScore = {
  university_id: string;
  score: number;
  status: 'green' | 'yellow' | 'red';
  breakdown: Record<'tasks' | 'documents' | 'stages' | 'teachers' | 'launch', number>;
  reasons: Array<{ code: string; severity: 'high' | 'medium' | 'low'; text: string }>;
  calculated_at: string;
  input_counters: Record<string, number>;
};

type ApiHealthSnapshot = { score: number; calculated_at: string };

function unwrap<T>(result: Awaited<ReturnType<typeof apiFetch<T>>>, message: string): T {
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, message, result.error);
}

async function passport(id: string, include = ''): Promise<ApiPassport> {
  const suffix = include ? `?include=${encodeURIComponent(include)}` : '';
  return unwrap(await apiFetch<ApiPassport>(`/api/v1/universities/${encodeURIComponent(id)}/passport${suffix}`), 'Не удалось загрузить паспорт ВУЗа.');
}

function responsible(value: string | null): UniversityResponsible | null {
  return value ? { id: `responsible:${value}`, name: value } : null;
}

function mapProgram(item: ApiProgram): UniversityProgramRow {
  return {
    id: item.id,
    direction: item.direction_name,
    name: item.name,
    status: item.status,
    launchDate: item.launch_date ?? '',
    responsible: responsible(item.responsible_name),
    teachersCount: item.teachers_count,
    studentsCount: item.students_count,
  };
}

function mapTeacher(item: ApiTeacher): UniversityTeacherRow {
  return {
    id: item.id,
    name: item.full_name,
    position: item.position,
    readiness: item.readiness,
    nextTrainingDate: item.next_qualification_date,
    allowedPrograms: item.programs.map((program) => program.name),
  };
}

export async function realGetUniversities(params: UniversityListQuery): Promise<PaginatedResult<UniversityListItem>> {
  const search = new URLSearchParams({ page: String(params.page), page_size: String(params.pageSize) });
  const filters: UniversityFilters = params.filters;
  if (filters.search) search.set('search', filters.search);
  if (filters.city) search.set('city', filters.city);
  if (filters.responsibleIds.length === 1) search.set('responsible_id', filters.responsibleIds[0]);
  const supportedSort = params.sort === 'last_interaction' ? 'created_at' : 'name';
  search.set('sort_by', supportedSort);
  search.set('sort_order', params.order);
  const page = unwrap(await apiFetch<ApiPage<ApiUniversity>>(`/api/v1/universities?${search}`), 'Не удалось загрузить список ВУЗов.');
  let scores = new Map<string, number>();
  if (page.items.length) {
    const batch = await apiFetch<{ items: Array<{ university_id: string; score: number }> }>(`/api/v1/universities/health-score?ids=${encodeURIComponent(page.items.map((item) => item.id).join(','))}`);
    if (batch.ok) scores = new Map(batch.data.items.map((item) => [item.university_id, item.score]));
  }
  return {
    items: page.items.map((item) => ({
      id: item.id,
      name: item.name,
      city: item.city ?? '—',
      responsible: null,
      programsCount: 0,
      programStatusCounts: {},
      currentStage: { id: 'preparation', name: 'Подготовка', tone: 'neutral' },
      healthScore: scores.get(item.id) ?? 0,
      lastInteractionAt: item.updated_at || item.created_at,
      attention: (scores.get(item.id) ?? 100) < 60,
    })),
    page: page.page,
    pageSize: page.page_size,
    total: page.total,
  };
}

export async function realGetUniversityPassport(id: string): Promise<UniversityPassport> {
  const data = await passport(id, 'health_score');
  const totalSteps = 100;
  const workflowStatus: UniversityPassport['workflow']['status'] = data.workflow_summary.overdue_stages > 0 ? 'attention' : data.workflow_summary.progress_percent >= 100 ? 'completed' : 'in_progress';
  return {
    id: data.university.id,
    name: data.university.name,
    city: data.university.city ?? '—',
    healthScore: data.health_score?.score ?? 0,
    metrics: {
      activePrograms: data.programs.filter((item) => item.status === 'active' || item.status === 'launched').length,
      teachers: { total: data.teachers.length, ready: data.teachers.filter((item) => item.readiness === 'ready').length, attention: data.teachers.filter((item) => item.readiness !== 'ready').length },
      licenses: { active: data.licenses.filter((item) => item.status === 'active').length, expiring: data.licenses.filter((item) => item.status === 'expires_soon').length, overdue: data.licenses.filter((item) => item.status === 'expired').length },
      documents: { total: data.documents.length, signed: data.documents.filter((item) => item.status === 'signed').length, overdue: data.documents.filter((item) => item.status === 'archived').length },
    },
    workflow: {
      currentStage: { id: data.workflow_summary.instance_id ?? 'not-started', name: data.workflow_summary.current_stage ?? 'Не запущен', tone: workflowStatus === 'attention' ? 'warning' : workflowStatus === 'completed' ? 'success' : 'brand' },
      status: workflowStatus,
      deadline: data.workflow_summary.next_due_date ?? '',
      overdue: data.workflow_summary.overdue_stages > 0,
      responsible: data.responsibles[0] ? { id: data.responsibles[0].id, name: data.responsibles[0].full_name, email: data.responsibles[0].email, role: data.responsibles[0].role } : null,
      completedSteps: Math.round(data.workflow_summary.progress_percent),
      totalSteps,
      nextStage: null,
    },
    timeline: data.last_interactions.map((item) => ({
      id: item.id,
      type: item.type === 'workflow_transition' ? 'workflow' : item.type === 'meeting' || item.type === 'document' || item.type === 'note' ? item.type : 'note',
      occurredAt: item.created_at,
      description: item.description ?? item.title,
    })),
  };
}

export async function realGetUniversityPrograms(id: string): Promise<UniversityProgramRow[]> {
  const data = unwrap(await apiFetch<ApiPage<ApiProgram>>(`/api/v1/universities/${encodeURIComponent(id)}/passport/programs?page=1&page_size=100`), 'Не удалось загрузить программы ВУЗа.');
  return data.items.map(mapProgram);
}

export async function realGetUniversityTeachers(id: string): Promise<UniversityTeacherRow[]> {
  const data = unwrap(await apiFetch<ApiPage<ApiTeacher>>(`/api/v1/universities/${encodeURIComponent(id)}/passport/teachers?page=1&page_size=100`), 'Не удалось загрузить преподавателей ВУЗа.');
  return data.items.map(mapTeacher);
}

export async function realGetUniversityStudentsSummary(id: string): Promise<UniversityStudentsSummary> {
  const data = (await passport(id)).students_summary;
  return {
    total: data.total,
    active: data.active,
    graduated: data.graduated,
    academicLeave: data.by_status.academic_leave ?? 0,
    byProgram: data.by_program.map((item) => ({ programId: item.program_id, programName: item.program_name, active: item.active, graduated: item.graduated, total: item.total })),
  };
}

export async function realGetUniversityProducts(id: string): Promise<UniversityProductRow[]> {
  const data = (await passport(id)).products;
  return data.map((item) => ({
    id: item.id,
    name: item.name,
    version: item.version,
    vendor: item.vendor_name,
    status: item.status === 'expired' ? 'expired' : item.status === 'active' ? 'active' : 'expiring',
    licenseNumber: item.license?.license_number ?? '—',
    expiresAt: item.license?.expires_at ?? '',
  }));
}

export async function realGetUniversityLicenses(id: string): Promise<UniversityLicenseRow[]> {
  const data = (await passport(id)).licenses;
  return data.map((item) => ({
    id: item.id,
    product: item.product_name,
    vendor: item.vendor_name,
    licenseNumber: item.license_number,
    signedAt: item.signed_at,
    expiresAt: item.expires_at,
    status: item.status === 'expired' ? 'expired' : item.status === 'expires_soon' ? 'expires_soon' : 'active',
    transfer: item.transfer_status,
    contract: item.contract_number ?? '—',
  }));
}

export async function realGetUniversityDocuments(id: string): Promise<UniversityDocumentRow[]> {
  const data = (await passport(id)).documents;
  return data.map((item) => ({
    id: item.id,
    type: item.document_type,
    name: item.title,
    fileName: item.file_name,
    fileSize: item.file_size ? `${Math.max(1, Math.round(item.file_size / 1024))} КБ` : '0 КБ',
    signedAt: item.signed_at,
    expiresAt: item.expires_at,
    status: item.status === 'signed' ? 'signed' : item.status === 'archived' ? 'expired' : 'pending',
    uploadedBy: item.uploaded_by,
    uploadedAt: item.created_at,
  }));
}

export async function realGetUniversityMeetings(id: string): Promise<UniversityMeetingRow[]> {
  const data = (await passport(id)).meetings;
  return data.map((item) => ({
    id: item.id,
    occurredAt: item.meeting_at,
    type: item.meeting_type === 'offline' || item.meeting_type === 'phone' || item.meeting_type === 'email' ? item.meeting_type : 'online',
    subject: item.subject,
    participants: item.participants.map((name, index) => ({ id: `${item.id}:${index}`, name, initials: name.split(/\s+/).slice(0, 2).map((part) => part[0]).join('') })),
    outcome: item.outcome ?? '—',
    nextAction: item.next_action ?? '—',
    dueDate: item.next_action_due,
    author: item.created_by,
  }));
}

export async function realGetUniversityResponsibles(id: string): Promise<UniversityResponsibleContact[]> {
  const data = (await passport(id)).responsibles;
  return data.map((item, index) => ({
    id: item.id,
    name: item.full_name,
    role: item.role,
    email: item.email,
    phone: item.phone ?? '—',
    isPrimary: index === 0,
    initials: item.full_name.split(/\s+/).slice(0, 2).map((part) => part[0]).join(''),
  }));
}

export async function realGetUniversityHistory(id: string, filters: UniversityHistoryFilters): Promise<UniversityHistoryEvent[]> {
  const data = await passport(id, 'audit');
  const defaultUser: UniversityResponsible = data.responsibles[0]
    ? { id: data.responsibles[0].id, name: data.responsibles[0].full_name, email: data.responsibles[0].email, role: data.responsibles[0].role }
    : { id: 'system', name: 'Система' };
  return data.last_interactions.map((item): UniversityHistoryEvent => ({
    id: item.id,
    occurredAt: item.created_at,
    type: item.type === 'workflow_transition' ? 'workflow' : item.type === 'meeting' || item.type === 'document' || item.type === 'note' ? item.type : 'audit',
    user: { ...defaultUser, name: item.author || defaultUser.name },
    action: item.title,
    details: item.description ?? item.title,
    entity: { id: item.id, label: item.title },
  })).filter((event) => {
    const date = event.occurredAt.slice(0, 10);
    if (filters.type !== 'all' && event.type !== filters.type) return false;
    if (filters.dateFrom && date < filters.dateFrom) return false;
    if (filters.dateTo && date > filters.dateTo) return false;
    if (filters.userId && event.user.id !== filters.userId) return false;
    if (filters.entityId && event.entity.id !== filters.entityId) return false;
    return true;
  });
}

const breakdownMeta = {
  tasks: { label: 'Задачи', weight: 25 },
  documents: { label: 'Документы', weight: 20 },
  stages: { label: 'Этапы', weight: 20 },
  teachers: { label: 'Преподаватели', weight: 20 },
  launch: { label: 'Запуск', weight: 15 },
} as const;

export async function realGetUniversityHealthScore(id: string): Promise<UniversityHealthScore> {
  const [scoreResult, historyResult] = await Promise.all([
    apiFetch<ApiHealthScore>(`/api/v1/universities/${encodeURIComponent(id)}/health-score`),
    apiFetch<ApiHealthSnapshot[]>(`/api/v1/universities/${encodeURIComponent(id)}/health-score/history?days=30`),
  ]);
  const score = unwrap(scoreResult, 'Не удалось загрузить Health Score.');
  const history = historyResult.ok
    ? historyResult.data.map((item) => ({ date: item.calculated_at.slice(0, 10), score: item.score })).reverse()
    : [];
  const points = history.length ? history : [{ date: score.calculated_at.slice(0, 10), score: score.score }];
  return {
    universityId: score.university_id,
    currentScore: score.score,
    status: getHealthStatus(score.score),
    breakdown: (Object.keys(breakdownMeta) as Array<keyof typeof breakdownMeta>).map((key) => ({
      id: key,
      label: breakdownMeta[key].label,
      weight: breakdownMeta[key].weight,
      score: score.breakdown[key],
      inputCounters: Object.entries(score.input_counters).map(([label, value]) => ({ label, value })),
    })),
    reasons: score.reasons.map((reason) => ({ id: reason.code, severity: reason.severity, title: reason.text, description: reason.text })),
    history: points,
    previousSnapshot: points[Math.max(0, points.length - 2)],
  };
}

type ApiTeacherPassport = {
  teacher: { id: string; university_id: string; full_name: string; email: string; position: string };
  university: { id: string; name: string; city: string | null };
  qualifications: Array<{ id: string; qualification_name: string; obtained_at: string; expires_at: string | null; document_ref: string | null }>;
  certificates: Array<{ id: string; certificate_name: string; issued_by: string; issued_at: string; expires_at: string | null; is_mandatory: boolean; program: { name: string } | null; document_ref: string | null }>;
  programs: Array<{ id: string; program: { id: string; name: string; direction_name: string }; can_teach: boolean; assigned_at: string }>;
  readiness: TeacherReadiness;
  readiness_reasons: string[];
  next_qualification_date: string | null;
};

export async function realGetTeacherPassport(id: string): Promise<TeacherPassport> {
  const data = unwrap(await apiFetch<ApiTeacherPassport>(`/api/v1/teachers/${encodeURIComponent(id)}/passport`), 'Не удалось загрузить паспорт преподавателя.');
  const qualifications: TeacherQualification[] = data.qualifications.map((item) => {
    const expiresAt = item.expires_at ?? item.obtained_at;
    return {
      id: item.id,
      name: item.qualification_name,
      obtainedAt: item.obtained_at,
      expiresAt,
      status: item.expires_at ? getExpirationStatus(item.expires_at) : 'current',
      document: item.document_ref ? { name: item.document_ref, fileType: 'Документ', fileSize: '—', downloadUrl: null } : null,
    };
  });
  const certificates: TeacherCertificate[] = data.certificates.map((item) => ({
    id: item.id,
    name: item.certificate_name,
    issuer: item.issued_by,
    issuedAt: item.issued_at,
    expiresAt: item.expires_at,
    mandatory: item.is_mandatory,
    program: item.program?.name ?? null,
    status: item.expires_at ? getExpirationStatus(item.expires_at) : 'no_expiry',
    document: item.document_ref ? { name: item.document_ref, fileType: 'Документ', fileSize: '—', downloadUrl: null } : null,
  }));
  return {
    teacher: {
      id: data.teacher.id,
      name: data.teacher.full_name,
      position: data.teacher.position,
      readiness: data.readiness,
      allowedPrograms: data.programs.map((item) => item.program.name),
      universityId: data.university.id,
      universityName: data.university.name,
      universityCity: data.university.city ?? '—',
      readinessReason: data.readiness_reasons.join(' · ') || 'Данные актуальны',
      nextTrainingDate: data.next_qualification_date,
      qualificationRequired: data.next_qualification_date !== null || data.readiness !== 'ready',
    },
    qualifications,
    trainings: [],
    certificates,
    allowedPrograms: data.programs.map((item) => ({
      id: item.program.id,
      name: item.program.name,
      direction: item.program.direction_name,
      canTeach: item.can_teach,
      assignedAt: item.assigned_at,
      status: 'active',
    })),
  };
}

// --------------------------------------------------------------------- import

export async function realUploadImportPreview(file: File, signal?: AbortSignal, onProgress?: (value: number) => void): Promise<ImportPreviewResponse> {
  const formData = new FormData();
  formData.append('file', file, file.name);
  const result = await apiUploadFormData<ImportPreviewResponse>('/api/v1/import/preview', formData, { signal, onProgress });
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить файл и построить предпросмотр.', result.error);
}

export async function realExecuteImport(fileId: string, mapping: Record<string, string>, options: ImportOptions): Promise<ImportExecuteResponse> {
  return unwrap(await apiFetch<ImportExecuteResponse>('/api/v1/import/execute', {
    method: 'POST',
    body: { file_id: fileId, mapping, options },
  }), 'Не удалось запустить импорт.');
}

export async function realGetImportJob(jobId: string): Promise<unknown> {
  return unwrap(await apiFetch<unknown>(`/api/v1/import/jobs/${encodeURIComponent(jobId)}`), 'Не удалось обновить статус импорта.');
}

export async function realListImportJobs(): Promise<unknown[]> {
  const result = await apiFetch<unknown>('/api/v1/import/jobs');
  if (!result.ok && result.status === 404) return [];
  const data = unwrap(result, 'Не удалось загрузить журнал импортов.');
  if (Array.isArray(data)) return data;
  return data && typeof data === 'object' && 'items' in data && Array.isArray(data.items) ? data.items : [];
}
