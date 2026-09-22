import type { ProgramStatus, TeacherReadiness, UniversityDocumentStatus, UniversityHistoryEventType, UniversityLicenseStatus, UniversityPassportWorkflow, UniversityProductStatus, UniversityWorkflowStageStatus } from './universities-repository';
import type { AttentionItem } from './dashboard-repository';

export type SemanticIntent = 'neutral' | 'brand' | 'success' | 'warning' | 'danger';

export const programStatusIntent: Record<ProgramStatus, SemanticIntent> = { planned: 'neutral', active: 'brand', launched: 'success', archived: 'neutral' };
export const readinessIntent: Record<TeacherReadiness, SemanticIntent> = { ready: 'success', attention: 'warning', expired: 'danger' };
export const licenseStatusIntent: Record<UniversityLicenseStatus, SemanticIntent> = { active: 'success', expires_soon: 'warning', expired: 'danger' };
export const documentStatusIntent: Record<UniversityDocumentStatus, SemanticIntent> = { signed: 'success', pending: 'warning', expired: 'danger' };
export const productStatusIntent: Record<UniversityProductStatus, SemanticIntent> = { active: 'success', expiring: 'warning', expired: 'danger' };
export const workflowStatusIntent: Record<UniversityPassportWorkflow['status'], SemanticIntent> = { in_progress: 'brand', completed: 'success', attention: 'warning' };
export const workflowStageStatusIntent: Record<UniversityWorkflowStageStatus, SemanticIntent> = { completed: 'success', current: 'brand', pending: 'neutral', skipped: 'neutral', overdue: 'danger' };
export const workflowStageStatusLabels: Record<UniversityWorkflowStageStatus, string> = { completed: 'Завершён', current: 'Текущий', pending: 'Ожидает', skipped: 'Пропущен', overdue: 'Просрочен' };
export const historyEventTypeLabels: Record<UniversityHistoryEventType, string> = { workflow: 'Workflow', document: 'Документ', meeting: 'Встреча', note: 'Заметка', audit: 'Аудит' };
export const historyEventTypeIntent: Record<UniversityHistoryEventType, SemanticIntent> = { workflow: 'brand', document: 'neutral', meeting: 'brand', note: 'neutral', audit: 'warning' };
export const attentionSeverityIntent: Record<AttentionItem['severity'], SemanticIntent> = { red: 'danger', orange: 'warning', yellow: 'warning' };
