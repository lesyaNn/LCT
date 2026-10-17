import type { FieldPath, FieldValues, UseFormSetError, UseFormSetFocus } from 'react-hook-form';

export const GENERIC_ERROR_MESSAGE = 'Не удалось выполнить действие. Попробуйте ещё раз.';

export const ERROR_MESSAGES = {
  WORKFLOW_INVALID_TRANSITION: 'Нельзя перейти на этот этап. Проверьте порядок этапов.',
  WORKFLOW_TASKS_INCOMPLETE: 'Нельзя завершить этап: есть невыполненные задачи.',
  FILE_TYPE_NOT_ALLOWED: 'Тип файла не разрешён.',
  FILE_TOO_LARGE: 'Файл слишком большой. Максимальный размер — 50 MB.',
  DUPLICATE_ENTITY: 'Такая запись уже существует.',
  ENTITY_NOT_FOUND: 'Объект не найден или был удалён.',
  REPORT_FAILED: 'Не удалось сформировать отчёт. Попробуйте уменьшить период или изменить фильтры.',
  EXTERNAL_SOURCE_UNAVAILABLE: 'Внешний источник временно недоступен. Показаны доступные данные.',
} as const;

export function incompleteWorkflowTasksMessage(count: number): string {
  if (!Number.isInteger(count) || count < 1) return ERROR_MESSAGES.WORKFLOW_TASKS_INCOMPLETE;
  const form = new Intl.PluralRules('ru-RU').select(count);
  const noun = form === 'one' ? 'невыполненная задача' : form === 'few' ? 'невыполненные задачи' : 'невыполненных задач';
  return `Нельзя завершить этап: ${form === 'one' ? 'осталась' : 'осталось'} ${count} ${noun}.`;
}

export type BusinessErrorCode = keyof typeof ERROR_MESSAGES;
export type NormalizedApiErrorKind = 'validation' | 'business' | 'permission' | 'authentication' | 'not-found' | 'network' | 'generic';

export interface NormalizedFieldError {
  field: string;
  message: string;
  code?: string;
}

export interface NormalizedApiError {
  kind: NormalizedApiErrorKind;
  status: number;
  code?: string;
  message: string;
  fieldErrors: NormalizedFieldError[];
  details: Record<string, unknown>;
}

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
    fallbackMessage = GENERIC_ERROR_MESSAGE,
    readonly transportMessage?: string,
  ) {
    super(fallbackMessage);
    this.name = 'ApiRequestError';
  }
}

type ErrorSource = { status: number; body?: unknown; message?: string };
type RecordValue = Record<string, unknown>;

function isRecord(value: unknown): value is RecordValue {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function errorSource(error: unknown): ErrorSource {
  if (error instanceof ApiRequestError) return { status: error.status, body: error.body, message: error.message };
  if (isRecord(error)) {
    return {
      status: typeof error.status === 'number' ? error.status : 0,
      body: error.body ?? error.data ?? (isRecord(error.response) ? error.response.data : undefined),
      message: stringValue(error.message),
    };
  }
  return { status: 0 };
}

function responseDetail(body: unknown): unknown {
  if (!isRecord(body)) return body;
  if ('detail' in body) return body.detail;
  if (isRecord(body.error)) return body.error;
  return body;
}

function responseDetails(body: unknown): Record<string, unknown> {
  if (!isRecord(body)) return {};
  const envelope = isRecord(body.error) ? body.error : isRecord(body.detail) ? body.detail : body;
  if (!isRecord(envelope.details)) return {};
  return Object.fromEntries(Object.entries(envelope.details).filter(([key]) => key !== 'field_errors'));
}

function responseMessage(body: unknown): string | undefined {
  if (!isRecord(body)) return undefined;
  const envelope = isRecord(body.error) ? body.error : isRecord(body.detail) ? body.detail : body;
  return stringValue(envelope.message);
}

function extractCode(body: unknown): string | undefined {
  if (!isRecord(body)) return undefined;
  const direct = stringValue(body.code);
  if (direct) return direct.toUpperCase();
  if (isRecord(body.error)) return stringValue(body.error.code)?.toUpperCase();
  if (isRecord(body.detail)) return stringValue(body.detail.code)?.toUpperCase();
  return undefined;
}

function fieldFromLocation(value: unknown): string | undefined {
  if (typeof value === 'string') return value.replace(/^body\./, '');
  if (!Array.isArray(value)) return undefined;
  const parts = value.filter((part): part is string | number => typeof part === 'string' || typeof part === 'number');
  const bodyIndex = parts.lastIndexOf('body');
  return parts.slice(bodyIndex >= 0 ? bodyIndex + 1 : 0).join('.');
}

function translatedValidationMessage(item: RecordValue): string {
  const type = stringValue(item.type) ?? '';
  const context = isRecord(item.ctx) ? item.ctx : {};
  if (type === 'missing' || type.endsWith('.missing')) return 'Обязательное поле.';
  if (type.includes('string_too_short') || type.includes('min_length')) {
    const minimum = context.min_length;
    return typeof minimum === 'number' ? `Минимум ${minimum} символов.` : 'Значение слишком короткое.';
  }
  if (type.includes('string_too_long') || type.includes('max_length')) {
    const maximum = context.max_length;
    return typeof maximum === 'number' ? `Максимум ${maximum} символов.` : 'Значение слишком длинное.';
  }
  if (type.includes('greater_than_equal')) {
    const minimum = context.ge;
    return typeof minimum === 'number' ? `Значение должно быть не меньше ${minimum}.` : 'Значение меньше допустимого.';
  }
  if (type.includes('uuid')) return 'Некорректный идентификатор.';
  if (type.includes('date')) return 'Укажите корректную дату.';
  return 'Некорректное значение.';
}

function isSafeUserMessage(value: string | undefined): value is string {
  return Boolean(value && value.length <= 300 && !/(traceback|stack trace|sql|pydantic|exception|internal server|syntaxerror|typeerror)/i.test(value));
}

function validationItems(body: unknown): NormalizedFieldError[] {
  const detail = responseDetail(body);
  const backendDetails = isRecord(detail) && isRecord(detail.details) ? detail.details : undefined;
  const candidates = Array.isArray(detail)
    ? detail
    : backendDetails && Array.isArray(backendDetails.field_errors) ? backendDetails.field_errors
    : isRecord(body) && Array.isArray(body.errors) ? body.errors
      : isRecord(detail) && Array.isArray(detail.errors) ? detail.errors
        : isRecord(detail) && (detail.field || detail.loc) ? [detail]
          : isRecord(body) && (body.field || body.loc) ? [body]
            : [];
  return candidates.flatMap((candidate) => {
    if (!isRecord(candidate)) return [];
    const field = fieldFromLocation(candidate.field ?? candidate.loc);
    if (!field) return [];
    const code = stringValue(candidate.code ?? candidate.type)?.toUpperCase();
    const directMessage = stringValue(candidate.message)?.replace(/^Value error,\s*/i, '');
    const translatedMessage = translatedValidationMessage(candidate);
    return [{
      field,
      message: translatedMessage !== 'Некорректное значение.'
        ? translatedMessage
        : directMessage && isSafeUserMessage(directMessage) ? directMessage : translatedMessage,
      code,
    }];
  });
}

function looksLikeWorkflowTransition(detail: unknown): boolean {
  const value = stringValue(detail)?.toLowerCase() ?? '';
  return ['transition', 'target workflow stage', 'required stages', 'current stage'].some((part) => value.includes(part));
}

export function normalizeApiError(error: unknown, options: { defaultCode?: BusinessErrorCode; fallbackMessage?: string } = {}): NormalizedApiError {
  const source = errorSource(error);
  const status = source.status;
  const body = source.body;
  const details = responseDetails(body);
  const fieldErrors = status === 422 ? validationItems(body) : [];
  const receivedCode = extractCode(body);
  let code = receivedCode;
  if (!code && (status === 413)) code = 'FILE_TOO_LARGE';
  if (!code && (status === 415)) code = 'FILE_TYPE_NOT_ALLOWED';
  if (!code && status === 404) code = 'ENTITY_NOT_FOUND';
  if (!code && status === 409 && options.defaultCode) code = options.defaultCode;
  if (!code && status === 422 && looksLikeWorkflowTransition(responseDetail(body))) code = 'WORKFLOW_INVALID_TRANSITION';

  if (fieldErrors.length) return { kind: 'validation', status, code: code ?? 'VALIDATION_ERROR', message: 'Исправьте ошибки в форме.', fieldErrors, details };
  if (status === 401) return { kind: 'authentication', status, code, message: 'Сессия истекла. Войдите снова.', fieldErrors: [], details };
  if (status === 403) return { kind: 'permission', status, code, message: 'Нет прав.', fieldErrors: [], details };
  if (status === 404) return { kind: 'not-found', status, code, message: ERROR_MESSAGES.ENTITY_NOT_FOUND, fieldErrors: [], details };
  if (status === 0) return { kind: 'network', status, code, message: 'Не удалось связаться с сервером. Проверьте соединение.', fieldErrors: [], details };
  if (code === 'WORKFLOW_TASKS_INCOMPLETE') return { kind: 'business', status, code, message: incompleteWorkflowTasksMessage(details.remaining_tasks as number), fieldErrors: [], details };
  if (code && code in ERROR_MESSAGES) return { kind: 'business', status, code, message: ERROR_MESSAGES[code as BusinessErrorCode], fieldErrors: [], details };
  const backendMessage = responseMessage(body);
  if (code && status < 500 && isSafeUserMessage(backendMessage)) return { kind: 'business', status, code, message: backendMessage, fieldErrors: [], details };
  if (status === 409) return { kind: 'business', status, code, message: ERROR_MESSAGES.DUPLICATE_ENTITY, fieldErrors: [], details };
  if (status === 422) return { kind: 'validation', status, code: code ?? 'VALIDATION_ERROR', message: 'Проверьте введённые данные.', fieldErrors: [], details };
  return { kind: 'generic', status, code, message: options.fallbackMessage ?? GENERIC_ERROR_MESSAGE, fieldErrors: [], details };
}

export function applyServerErrorsToForm<TFieldValues extends FieldValues>(
  normalized: NormalizedApiError,
  options: {
    fields: readonly FieldPath<TFieldValues>[];
    fieldMap?: Readonly<Record<string, FieldPath<TFieldValues>>>;
    setError: UseFormSetError<TFieldValues>;
    setFocus: UseFormSetFocus<TFieldValues>;
  },
): { applied: boolean; hasUnknownFields: boolean } {
  const known = new Set<string>(options.fields);
  const mapped: Array<{ name: FieldPath<TFieldValues>; message: string }> = [];
  let hasUnknownFields = false;
  for (const error of normalized.fieldErrors) {
    const leaf = error.field.split('.').at(-1) ?? error.field;
    const candidate = options.fieldMap?.[error.field] ?? options.fieldMap?.[leaf] ?? leaf;
    if (!known.has(candidate)) { hasUnknownFields = true; continue; }
    mapped.push({ name: candidate as FieldPath<TFieldValues>, message: error.message });
  }
  for (const error of mapped) options.setError(error.name, { type: 'server', message: error.message });
  if (mapped[0]) options.setFocus(mapped[0].name);
  return { applied: mapped.length > 0, hasUnknownFields };
}
