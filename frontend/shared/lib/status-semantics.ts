export type SemanticIntent = 'neutral' | 'brand' | 'success' | 'warning' | 'danger';

export const programStatusIntent: Record<string, SemanticIntent> = { planned: 'neutral', active: 'brand', launched: 'success', archived: 'neutral' };
export const readinessIntent: Record<string, SemanticIntent> = { ready: 'success', attention: 'warning', expired: 'danger' };
export const licenseStatusIntent: Record<string, SemanticIntent> = { active: 'success', expires_soon: 'warning', expired: 'danger' };
export const documentStatusIntent: Record<string, SemanticIntent> = { signed: 'success', pending: 'warning', expired: 'danger' };
export const productStatusIntent: Record<string, SemanticIntent> = { active: 'success', expiring: 'warning', expired: 'danger' };
