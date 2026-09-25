'use client';

import { useEffect, useId, useMemo, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { applyServerErrorsToForm, normalizeApiError, type NormalizedApiError } from '@/shared/lib/api-errors';
import {
  catalogDefinition,
  catalogQueryKeys,
  getCatalogItem,
  type CatalogInput,
  type CatalogItem,
  type CatalogReferenceData,
  type CatalogType,
} from '@/shared/lib/catalogs-repository';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner, FormField } from '@/shared/ui/rtk/form-field';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import styles from './catalogs-page.module.css';

const required = (max: number, message: string) => z.string().max(max, `Максимум ${max} символов.`).refine((value) => value.trim().length > 0, message);
const schemas = {
  universities: z.object({ name: required(512, 'Укажите название ВУЗа.'), city: z.string().max(256, 'Максимум 256 символов.') }),
  products: z.object({ name: required(512, 'Укажите название продукта.'), vendorId: required(64, 'Выберите вендора.'), version: z.string().max(128, 'Максимум 128 символов.') }),
  directions: z.object({ name: required(512, 'Укажите название направления.'), code: required(64, 'Укажите код направления.') }),
  responsibles: z.object({ name: required(512, 'Укажите ФИО.'), email: required(512, 'Укажите email.'), phone: z.string().max(64, 'Максимум 64 символа.'), role: z.string().max(256, 'Максимум 256 символов.'), universityIds: z.array(z.string()) }),
} as const;

type CatalogFormValues = {
  name: string;
  city: string;
  vendorId: string;
  version: string;
  code: string;
  email: string;
  phone: string;
  role: string;
  universityIds: string[];
};

const allFieldsSchema = z.object({
  name: z.string(),
  city: z.string(),
  vendorId: z.string(),
  version: z.string(),
  code: z.string(),
  email: z.string(),
  phone: z.string(),
  role: z.string(),
  universityIds: z.array(z.string()),
});

function catalogFormSchema(type: CatalogType) {
  return allFieldsSchema.superRefine((values, context) => {
    const result = schemas[type].safeParse(values);
    if (result.success) return;
    for (const issue of result.error.issues) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: issue.path, message: issue.message });
    }
  });
}

const formFields = ['name', 'city', 'vendorId', 'version', 'code', 'email', 'phone', 'role', 'universityIds'] as const;

function valuesFor(type: CatalogType, item?: CatalogItem | null): CatalogFormValues {
  return {
    name: item?.name ?? '',
    city: item?.type === 'universities' ? item.city : '',
    vendorId: item?.type === 'products' ? item.vendorId : '',
    version: item?.type === 'products' ? item.version : '',
    code: item?.type === 'directions' ? item.code : '',
    email: item?.type === 'responsibles' ? item.email : '',
    phone: item?.type === 'responsibles' ? item.phone : '',
    role: item?.type === 'responsibles' ? item.role : '',
    universityIds: item?.type === 'responsibles' ? [...item.universityIds] : [],
  };
}

function inputFor(type: CatalogType, values: CatalogFormValues): CatalogInput {
  if (type === 'universities') return { type, name: values.name.trim(), city: values.city.trim() };
  if (type === 'products') return { type, name: values.name.trim(), vendorId: values.vendorId, version: values.version.trim() };
  if (type === 'directions') return { type, name: values.name.trim(), code: values.code.trim() };
  return { type, name: values.name.trim(), email: values.email.trim(), phone: values.phone.trim(), role: values.role.trim(), universityIds: values.universityIds };
}

function duplicateField(type: CatalogType): keyof CatalogFormValues {
  if (type === 'directions') return 'code';
  if (type === 'responsibles') return 'email';
  return 'name';
}

function fieldMap(type: CatalogType): Record<string, keyof CatalogFormValues> {
  return {
    full_name: 'name',
    vendor_id: 'vendorId',
    university_ids: 'universityIds',
    ...(type === 'directions' ? { direction_code: 'code' as const } : {}),
  };
}

export function CatalogFormModal({ type, item, references, pending, onClose, onSubmit, onError }: {
  type: CatalogType;
  item: CatalogItem | null;
  references: CatalogReferenceData;
  pending: boolean;
  onClose: () => void;
  onSubmit: (input: CatalogInput) => Promise<void>;
  onError: (error: NormalizedApiError) => void;
}) {
  const id = useId();
  const [serverError, setServerError] = useState<string | null>(null);
  const detailQuery = useQuery({
    queryKey: catalogQueryKeys.detail(type, item?.id ?? 'new'),
    queryFn: ({ signal }) => getCatalogItem(type, item!.id, signal),
    enabled: Boolean(item && type === 'responsibles'),
  });
  const effectiveItem = detailQuery.data ?? item;
  const resolver = useMemo(() => zodResolver(catalogFormSchema(type)), [type]);
  const { register, control, handleSubmit, reset, setError, setFocus, formState: { errors, submitCount } } = useForm<CatalogFormValues>({
    resolver,
    mode: 'onSubmit',
    reValidateMode: 'onChange',
    defaultValues: valuesFor(type, item),
  });

  useEffect(() => { reset(valuesFor(type, effectiveItem)); }, [effectiveItem, reset, type]);

  const submit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      await onSubmit(inputFor(type, values));
    } catch (cause) {
      const normalized = normalizeApiError(cause, { defaultCode: 'DUPLICATE_ENTITY', fallbackMessage: 'Не удалось сохранить запись каталога.' });
      if (normalized.status === 409 || normalized.code === 'DUPLICATE_ENTITY') {
        const field = duplicateField(type);
        setError(field, { type: 'server', message: field === 'email' ? 'Ответственный с таким email уже существует.' : field === 'code' ? 'Направление с таким кодом уже существует.' : 'Запись с таким названием уже существует.' });
        setFocus(field);
        setServerError('Исправьте ошибки в форме.');
        onError(normalized);
        return;
      }
      const mapped = applyServerErrorsToForm(normalized, { fields: formFields, fieldMap: fieldMap(type), setError, setFocus });
      if (normalized.kind === 'validation') setServerError(mapped.hasUnknownFields || !mapped.applied ? normalized.message : 'Исправьте ошибки в форме.');
      else { setServerError(normalized.message); onError(normalized); }
    }
  });

  const definition = catalogDefinition(type);
  const title = item ? `Редактировать ${definition.singular}` : `Добавить ${definition.singular}`;
  const showBanner = Boolean(serverError || (submitCount > 0 && Object.keys(errors).length));
  const field = (name: keyof CatalogFormValues) => ({ id: `${id}-${name}`, errorId: `${id}-${name}-error`, error: errors[name]?.message ? String(errors[name]?.message) : undefined });
  const nameField = field('name');
  const detailLoading = Boolean(item && type === 'responsibles' && detailQuery.isPending);

  return <Modal title={title} onClose={onClose} size="l"><form className={styles.catalogForm} onSubmit={submit} noValidate>
    {showBanner ? <FormErrorBanner>{serverError ?? undefined}</FormErrorBanner> : null}
    {detailQuery.isError ? <FormErrorBanner>Не удалось загрузить связи с ВУЗами. Закройте форму и попробуйте снова.</FormErrorBanner> : null}
    <FormField label={type === 'responsibles' ? 'ФИО' : 'Название'} htmlFor={nameField.id} required error={nameField.error} errorId={nameField.errorId}><Input id={nameField.id} autoFocus maxLength={512} disabled={pending || detailLoading} aria-invalid={Boolean(nameField.error)} aria-describedby={nameField.error ? nameField.errorId : undefined} {...register('name')} /></FormField>
    {type === 'universities' ? (() => { const meta = field('city'); return <FormField label="Город" htmlFor={meta.id} error={meta.error} errorId={meta.errorId} hint="В текущем University DTO отдельного поля «Регион» нет."><Input id={meta.id} maxLength={256} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('city')} /></FormField>; })() : null}
    {type === 'products' ? <div className={styles.formGrid}>{(() => { const meta = field('vendorId'); return <FormField label="Вендор" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('vendorId')}><option value="">Выберите вендора</option>{references.vendors.map((vendor) => <option value={vendor.id} key={vendor.id}>{vendor.name}</option>)}</Select></FormField>; })()}{(() => { const meta = field('version'); return <FormField label="Версия" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Input id={meta.id} maxLength={128} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('version')} /></FormField>; })()}</div> : null}
    {type === 'directions' ? (() => { const meta = field('code'); return <FormField label="Код" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Input id={meta.id} maxLength={64} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('code')} /></FormField>; })() : null}
    {type === 'responsibles' ? <><div className={styles.formGrid}>{(() => { const meta = field('email'); return <FormField label="Email" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Input id={meta.id} type="email" maxLength={512} disabled={pending || detailLoading} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('email')} /></FormField>; })()}{(() => { const meta = field('phone'); return <FormField label="Телефон" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Input id={meta.id} maxLength={64} disabled={pending || detailLoading} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('phone')} /></FormField>; })()}</div>{(() => { const meta = field('role'); return <FormField label="Роль" htmlFor={meta.id} error={meta.error} errorId={meta.errorId} hint="Свободное текстовое поле реального Responsible DTO."><Input id={meta.id} maxLength={256} disabled={pending || detailLoading} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('role')} /></FormField>; })()}<Controller control={control} name="universityIds" render={({ field: universityField }) => <div className={styles.multiField}><span>Доступные ВУЗы</span><MultiSelect label="ВУЗы" options={references.universities} values={universityField.value} onChange={universityField.onChange} searchable loading={detailLoading} disabled={pending || detailLoading || detailQuery.isError} /></div>} /></> : null}
    <div className={styles.modalActions}><Button type="button" variant="ghost" disabled={pending} onClick={onClose}>Отмена</Button><Button type="submit" variant="primary" loading={pending} disabled={pending || detailLoading || detailQuery.isError}>{item ? 'Сохранить' : 'Добавить'}</Button></div>
  </form></Modal>;
}
