import type { ProgramStatus, TeacherReadiness, UniversityDocumentStatus, UniversityLicenseStatus, UniversityPassportWorkflow, UniversityProductStatus } from './universities-repository';
import type { AttentionItem } from './dashboard-repository';

export type SemanticIntent = 'neutral' | 'brand' | 'success' | 'warning' | 'danger';

export const programStatusIntent: Record<ProgramStatus, SemanticIntent> = { planned: 'neutral', active: 'brand', launched: 'success', archived: 'neutral' };
export const readinessIntent: Record<TeacherReadiness, SemanticIntent> = { ready: 'success', attention: 'warning', expired: 'danger' };
export const licenseStatusIntent: Record<UniversityLicenseStatus, SemanticIntent> = { active: 'success', expires_soon: 'warning', expired: 'danger' };
export const documentStatusIntent: Record<UniversityDocumentStatus, SemanticIntent> = { signed: 'success', pending: 'warning', expired: 'danger' };
export const productStatusIntent: Record<UniversityProductStatus, SemanticIntent> = { active: 'success', expiring: 'warning', expired: 'danger' };
export const workflowStatusIntent: Record<UniversityPassportWorkflow['status'], SemanticIntent> = { in_progress: 'brand', completed: 'success', attention: 'warning' };
export const attentionSeverityIntent: Record<AttentionItem['severity'], SemanticIntent> = { red: 'danger', orange: 'warning', yellow: 'warning' };
