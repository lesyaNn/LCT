export function visibleWorkflowDescription(description: string | null): boolean {
  return Boolean(description && !/README|канонический маршрут/i.test(description));
}
