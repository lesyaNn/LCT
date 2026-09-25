import type { ExpirationStatus, UpcomingDateStatus } from './formatters';
import type { ProgramStatus, TeacherCertificateStatus, TeacherReadiness, UniversityDocumentStatus, UniversityHistoryEventType, UniversityLicenseStatus, UniversityPassportWorkflow, UniversityProductStatus, UniversityWorkflowStageStatus } from './universities-repository';
import type { AttentionItem } from './dashboard-repository';

export type SemanticIntent = 'neutral' | 'brand' | 'info' | 'success' | 'warning' | 'danger';
export type ReadinessIcon = 'success' | 'warning' | 'error';
export type WorkflowStageIcon = 'check' | 'information' | 'time' | 'skip' | 'error';

export const readinessSemantics: Record<TeacherReadiness, { label: string; intent: SemanticIntent; icon: ReadinessIcon }> = {
  ready: { label: 'Готов', intent: 'success', icon: 'success' },
  attention: { label: 'Требует внимания', intent: 'warning', icon: 'warning' },
  expired: { label: 'Просрочено', intent: 'danger', icon: 'error' },
};

export const programStatusIntent: Record<ProgramStatus, SemanticIntent> = { planned: 'neutral', active: 'brand', launched: 'success', archived: 'neutral' };
export const expirationStatusIntent: Record<ExpirationStatus, SemanticIntent> = { current: 'success', expires_soon: 'warning', expired: 'danger' };
export const expirationStatusLabels: Record<ExpirationStatus, string> = { current: 'Актуально', expires_soon: 'Скоро истекает', expired: 'Просрочено' };
export const certificateStatusIntent: Record<TeacherCertificateStatus, SemanticIntent> = { ...expirationStatusIntent, no_expiry: 'neutral' };
export const certificateStatusLabels: Record<TeacherCertificateStatus, string> = { ...expirationStatusLabels, no_expiry: 'Бессрочный' };
export const upcomingDateIntent: Record<UpcomingDateStatus, SemanticIntent> = { long_term: 'success', approaching: 'warning', urgent: 'danger', overdue: 'danger', unknown: 'neutral' };
export const licenseStatusIntent: Record<UniversityLicenseStatus, SemanticIntent> = { active: 'success', expires_soon: 'warning', expired: 'danger' };
export const documentStatusIntent: Record<UniversityDocumentStatus, SemanticIntent> = { signed: 'success', pending: 'warning', expired: 'danger', archived: 'neutral' };
export const productStatusIntent: Record<UniversityProductStatus, SemanticIntent> = { planned: 'neutral', active: 'success', expiring: 'warning', expired: 'danger' };
export const workflowStatusIntent: Record<UniversityPassportWorkflow['status'], SemanticIntent> = { in_progress: 'brand', completed: 'success', attention: 'warning' };
export const workflowStageStatusSemantics: Record<UniversityWorkflowStageStatus, { label: string; intent: SemanticIntent; icon: WorkflowStageIcon; muted: boolean; titleDecoration: 'none' | 'strike'; emphasis: 'default' | 'current' | 'error' }> = {
  completed: { label: 'Завершён', intent: 'success', icon: 'check', muted: false, titleDecoration: 'strike', emphasis: 'default' },
  current: { label: 'Текущий', intent: 'brand', icon: 'information', muted: false, titleDecoration: 'none', emphasis: 'current' },
  pending: { label: 'Ожидает', intent: 'neutral', icon: 'time', muted: false, titleDecoration: 'none', emphasis: 'default' },
  skipped: { label: 'Пропущен', intent: 'neutral', icon: 'skip', muted: true, titleDecoration: 'strike', emphasis: 'default' },
  overdue: { label: 'Просрочен', intent: 'danger', icon: 'error', muted: false, titleDecoration: 'none', emphasis: 'error' },
};
export const historyEventTypeLabels: Record<UniversityHistoryEventType, string> = { workflow: 'Workflow', document: 'Документ', meeting: 'Встреча', note: 'Заметка', audit: 'Аудит' };
export const historyEventTypeIntent: Record<UniversityHistoryEventType, SemanticIntent> = { workflow: 'brand', document: 'neutral', meeting: 'brand', note: 'neutral', audit: 'warning' };
export const attentionSeverityIntent: Record<AttentionItem['severity'], SemanticIntent> = { red: 'danger', orange: 'warning', yellow: 'warning' };
