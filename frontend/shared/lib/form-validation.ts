import { z } from 'zod';

export const emailField = (maxLength = 512) => z.string().trim().min(1, 'Обязательное поле').max(maxLength, `Максимум ${maxLength} символов.`).email('Введите корректный email');

export const phoneField = z.string().trim().max(64, 'Максимум 64 символа.').refine((value) => {
  if (!value) return true;
  const digits = value.replace(/\D/g, '').length;
  return /^\+?[0-9 ()-]+$/.test(value) && digits >= 5 && digits <= 20;
}, 'Введите номер телефона: 5–20 цифр, можно использовать +, пробелы, скобки и дефис.');

export function isValidIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export const optionalDateField = z.string().refine((value) => !value || isValidIsoDate(value), 'Укажите корректную дату.');
export const requiredDateField = z.string().min(1, 'Обязательное поле').refine(isValidIsoDate, 'Укажите корректную дату.');
