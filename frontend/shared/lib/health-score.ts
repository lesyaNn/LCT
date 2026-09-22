export type HealthStatus = 'green' | 'yellow' | 'red';

export const healthStatusMeta: Record<HealthStatus, { label: string; tone: 'success' | 'warning' | 'danger' }> = {
  green: { label: 'Зелёный', tone: 'success' },
  yellow: { label: 'Жёлтый', tone: 'warning' },
  red: { label: 'Красный', tone: 'danger' },
};

/** Единые пороги UI, совпадающие с backend health-score contract. */
export function getHealthStatus(score: number): HealthStatus {
  if (score >= 85) return 'green';
  if (score >= 60) return 'yellow';
  return 'red';
}

export function getHealthStatusLabel(status: HealthStatus): string {
  return healthStatusMeta[status].label;
}
