'use client';

import { useEffect, useId, useMemo, useState } from 'react';
import { Controller, useFieldArray, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { applyServerErrorsToForm, normalizeApiError, type NormalizedApiError } from '@/shared/lib/api-errors';
import {
  catalogDefinition,
  catalogQueryKeys,
  getCatalogItem,
  type CatalogInput,
  type AgreementKind,
  type CatalogItem,
  type CatalogReferenceData,
  type CatalogType,
} from '@/shared/lib/catalogs-repository';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner, FormField } from '@/shared/ui/rtk/form-field';
import { Input, Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import styles from './catalogs-page.module.css';

const required = (max: number, message: string) => z.string().max(max, `Максимум ${max} символов.`).refine((value) => value.trim().length > 0, message);
const schemas = {
  universities: z.object({ name: required(512, 'Укажите название ВУЗа.'), city: z.string().max(256, 'Максимум 256 символов.') }),
  products: z.object({ name: required(512, 'Укажите название продукта.'), vendorId: required(64, 'Выберите вендора.'), programId: z.string().max(64), version: z.string().max(128, 'Максимум 128 символов.') }),
  directions: z.object({ name: required(512, 'Укажите название направления.'), code: required(64, 'Укажите код направления.') }),
  programs: z.object({ name: required(512, 'Укажите название программы.'), directionId: required(64, 'Выберите направление.'), description: z.string().max(4000, 'Максимум 4000 символов.') }),
  vendors: z.object({ name: required(512, 'Укажите название вендора.'), vendorContacts: z.array(z.object({ fullName: required(512, 'Укажите контактное лицо.'), email: required(512, 'Укажите email.'), phone: z.string().max(64), communicationMethod: z.string().max(256) })) }),
  responsibles: z.object({ name: required(512, 'Укажите ФИО.'), email: required(512, 'Укажите email.'), phone: z.string().max(64, 'Максимум 64 символа.'), role: z.string().max(256, 'Максимум 256 символов.'), universityIds: z.array(z.string()) }),
  contracts: z.object({
    universityId: required(64, 'Выберите ВУЗ.'),
    contractNumber: required(64, 'Укажите номер договора.'),
    productId: z.string().max(64),
    signedAt: required(10, 'Укажите дату подписания.'),
    expiresAt: z.string().max(10),
    statusRaw: z.enum(['draft', 'signed', 'terminated']),
    transferStatus: z.enum(['pending', 'transferred', 'accepted', 'rejected']),
    comment: z.string().max(4000, 'Максимум 4000 символов.'),
  }),
  licenses: z.object({
    universityId: required(64, 'Выберите ВУЗ.'),
    licenseNumber: required(64, 'Укажите номер лицензии.'),
    productId: required(64, 'Выберите продукт.'),
    contractId: z.string().max(64),
    programId: z.string().max(64),
    directionId: z.string().max(64),
    signedAt: required(10, 'Укажите дату подписания.'),
    expiresAt: required(10, 'Укажите дату окончания.'),
    transferStatus: z.enum(['pending', 'transferred', 'accepted', 'rejected']),
    comment: z.string().max(4000, 'Максимум 4000 символов.'),
  }),
} as const;

const agreementSchemas = { contracts: schemas.contracts, licenses: schemas.licenses } as const;

type CatalogFormValues = {
  name: string;
  city: string;
  vendorId: string;
  programId: string;
  version: string;
  code: string;
  directionId: string;
  description: string;
  email: string;
  phone: string;
  role: string;
  universityIds: string[];
  vendorContacts: Array<{ fullName: string; email: string; phone: string; communicationMethod: string }>;
  universityId: string;
  contractNumber: string;
  licenseNumber: string;
  productId: string;
  contractId: string;
  signedAt: string;
  expiresAt: string;
  statusRaw: 'draft' | 'signed' | 'terminated';
  transferStatus: 'pending' | 'transferred' | 'accepted' | 'rejected';
  comment: string;
};

const allFieldsSchema = z.object({
  name: z.string(),
  city: z.string(),
  vendorId: z.string(),
  programId: z.string(),
  version: z.string(),
  code: z.string(),
  directionId: z.string(),
  description: z.string(),
  email: z.string(),
  phone: z.string(),
  role: z.string(),
  universityIds: z.array(z.string()),
  vendorContacts: z.array(z.object({ fullName: z.string(), email: z.string(), phone: z.string(), communicationMethod: z.string() })),
  universityId: z.string(),
  contractNumber: z.string(),
  licenseNumber: z.string(),
  productId: z.string(),
  contractId: z.string(),
  signedAt: z.string(),
  expiresAt: z.string(),
  statusRaw: z.enum(['draft', 'signed', 'terminated']),
  transferStatus: z.enum(['pending', 'transferred', 'accepted', 'rejected']),
  comment: z.string(),
});

function catalogFormSchema(type: CatalogType, kind: AgreementKind) {
  return allFieldsSchema.superRefine((values, context) => {
    const result = (type === 'agreements' ? agreementSchemas[kind] : schemas[type]).safeParse(values);
    if (result.success) return;
    for (const issue of result.error.issues) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: issue.path, message: issue.message });
    }
  });
}

const formFields = [
  'name', 'city', 'vendorId', 'programId', 'version', 'code', 'directionId', 'description', 'email', 'phone', 'role', 'universityIds',
  'universityId', 'contractNumber', 'licenseNumber', 'productId', 'contractId', 'signedAt', 'expiresAt', 'statusRaw', 'transferStatus', 'comment',
] as const;

function valuesFor(type: CatalogType, item?: CatalogItem | null): CatalogFormValues {
  return {
    name: item?.name ?? '',
    city: item?.type === 'universities' ? item.city : '',
    vendorId: item?.type === 'products' ? item.vendorId : '',
    programId: item?.type === 'products' ? item.programId : '',
    version: item?.type === 'products' ? item.version : '',
    code: item?.type === 'directions' ? item.code : '',
    directionId: item?.type === 'programs' || (item?.type === 'agreements' && item.kind === 'licenses') ? item.directionId : '',
    description: item?.type === 'programs' ? item.description : '',
    email: item?.type === 'responsibles' ? item.email : '',
    phone: item?.type === 'responsibles' ? item.phone : '',
    role: item?.type === 'responsibles' ? item.role : '',
    universityIds: item?.type === 'responsibles' ? [...item.universityIds] : [],
    vendorContacts: item?.type === 'vendors' ? (item.contacts ?? []).filter((contact) => !contact.productId).map((contact) => ({ fullName: contact.fullName, email: contact.email, phone: contact.phone, communicationMethod: contact.communicationMethod })) : [],
    universityId: item?.type === 'agreements' ? item.universityId : '',
    contractNumber: item?.type === 'agreements' && item.kind === 'contracts' ? item.contractNumber : '',
    licenseNumber: item?.type === 'agreements' && item.kind === 'licenses' ? item.licenseNumber : '',
    productId: item?.type === 'agreements' ? item.productId : '',
    contractId: item?.type === 'agreements' && item.kind === 'licenses' ? item.contractId : '',
    signedAt: item?.type === 'agreements' ? item.signedAt : '',
    expiresAt: item?.type === 'agreements' ? item.expiresAt : '',
    statusRaw: item?.type === 'agreements' && item.kind === 'contracts' ? item.statusRaw : ('signed' as const),
    transferStatus: item?.type === 'agreements' ? item.transferStatus : ('pending' as const),
    comment: item?.type === 'agreements' ? item.comment : '',
  };
}

function inputFor(type: CatalogType, kind: AgreementKind, values: CatalogFormValues): CatalogInput {
  if (type === 'universities') return { type, name: values.name.trim(), city: values.city.trim() };
  if (type === 'products') return { type, name: values.name.trim(), vendorId: values.vendorId, programId: values.programId, version: values.version.trim() };
  if (type === 'directions') return { type, name: values.name.trim(), code: values.code.trim() };
  if (type === 'programs') return { type, name: values.name.trim(), directionId: values.directionId, description: values.description.trim() };
  if (type === 'vendors') return { type, name: values.name.trim(), contacts: values.vendorContacts.map((contact) => ({ fullName: contact.fullName.trim(), email: contact.email.trim(), phone: contact.phone.trim(), communicationMethod: contact.communicationMethod.trim() })) };
  if (type === 'agreements' && kind === 'contracts') {
    return {
      type, kind, universityId: values.universityId, contractNumber: values.contractNumber.trim(), productId: values.productId,
      signedAt: values.signedAt, expiresAt: values.expiresAt, statusRaw: values.statusRaw, transferStatus: values.transferStatus, comment: values.comment.trim(),
    };
  }
  if (type === 'agreements' && kind === 'licenses') {
    return {
      type, kind, universityId: values.universityId, licenseNumber: values.licenseNumber.trim(), productId: values.productId,
      contractId: values.contractId, programId: values.programId, directionId: values.directionId,
      signedAt: values.signedAt, expiresAt: values.expiresAt, transferStatus: values.transferStatus, comment: values.comment.trim(),
    };
  }
  return { type: 'responsibles', name: values.name.trim(), email: values.email.trim(), phone: values.phone.trim(), role: values.role.trim(), universityIds: values.universityIds };
}

function duplicateField(type: CatalogType, kind: AgreementKind): keyof CatalogFormValues {
  if (type === 'directions') return 'code';
  if (type === 'responsibles') return 'email';
  if (type === 'agreements') return kind === 'contracts' ? 'contractNumber' : 'licenseNumber';
  return 'name';
}

function duplicateMessage(type: CatalogType, field: keyof CatalogFormValues): string {
  if (field === 'email') return 'Ответственный с таким email уже существует.';
  if (field === 'code') return 'Направление с таким кодом уже существует.';
  if (field === 'contractNumber') return 'Договор с таким номером уже существует.';
  if (field === 'licenseNumber') return 'Лицензия с таким номером уже существует.';
  if (type === 'vendors') return 'Вендор с таким названием уже существует.';
  if (type === 'programs') return 'В этом направлении уже есть программа с таким названием.';
  return 'Запись с таким названием уже существует.';
}

function fieldMap(type: CatalogType): Record<string, keyof CatalogFormValues> {
  return {
    full_name: 'name',
    vendor_id: 'vendorId',
    program_id: 'programId',
    direction_id: 'directionId',
    university_ids: 'universityIds',
    ...(type === 'directions' ? { direction_code: 'code' as const } : {}),
    ...(type === 'agreements' ? {
      university_id: 'universityId',
      contract_number: 'contractNumber',
      license_number: 'licenseNumber',
      product_id: 'productId',
      contract_id: 'contractId',
      program_id: 'programId',
      signed_at: 'signedAt',
      expires_at: 'expiresAt',
      status_raw: 'statusRaw',
      transfer_status_raw: 'transferStatus',
    } as const : {}),
  };
}

export function CatalogFormModal({ type, kind, item, references, pending, onClose, onSubmit, onError }: {
  type: CatalogType;
  /** Only meaningful for the combined agreements tab. */
  kind: AgreementKind;
  item: CatalogItem | null;
  references: CatalogReferenceData;
  pending: boolean;
  onClose: () => void;
  onSubmit: (input: CatalogInput) => Promise<void>;
  onError: (error: NormalizedApiError) => void;
}) {
  const id = useId();
  const [serverError, setServerError] = useState<string | null>(null);
  // Only responsibles need the detail round-trip: GET /responsibles omits the
  // university links, while the agreement list already carries every form
  // field. Fetching it anyway would reset the form and discard user input.
  const needsDetail = type === 'responsibles' || type === 'vendors';
  const detailQuery = useQuery({
    queryKey: catalogQueryKeys.detail(type, item?.id ?? 'new'),
    queryFn: ({ signal }) => getCatalogItem(type, item!.id, signal, kind),
    enabled: Boolean(item) && needsDetail,
  });
  const effectiveItem = detailQuery.data ?? item;
  const resolver = useMemo(() => zodResolver(catalogFormSchema(type, kind)), [type, kind]);
  const { register, control, handleSubmit, reset, setError, setFocus, formState: { errors, submitCount } } = useForm<CatalogFormValues>({
    resolver,
    mode: 'onSubmit',
    reValidateMode: 'onChange',
    defaultValues: valuesFor(type, item),
  });
  const { fields: vendorContactFields, append: addVendorContact, remove: removeVendorContact } = useFieldArray({ control, name: 'vendorContacts' });

  useEffect(() => { reset(valuesFor(type, effectiveItem)); }, [effectiveItem, reset, type]);

  const submit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      await onSubmit(inputFor(type, kind, values));
    } catch (cause) {
      const normalized = normalizeApiError(cause, { defaultCode: 'DUPLICATE_ENTITY', fallbackMessage: 'Не удалось сохранить запись каталога.' });
      if (normalized.status === 409 || normalized.code === 'DUPLICATE_ENTITY') {
        const field = duplicateField(type, kind);
        setError(field, { type: 'server', message: duplicateMessage(type, field) });
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
  const agreementSingular = kind === 'contracts' ? 'договор' : 'лицензию';
  const singular = type === 'agreements' ? agreementSingular : definition.singular;
  const title = item ? `Редактировать ${singular}` : `Добавить ${singular}`;
  const showBanner = Boolean(serverError || (submitCount > 0 && Object.keys(errors).length));
  const field = (name: keyof CatalogFormValues) => ({ id: `${id}-${name}`, errorId: `${id}-${name}-error`, error: errors[name]?.message ? String(errors[name]?.message) : undefined });
  const nameField = field('name');
  const detailLoading = Boolean(item && needsDetail && detailQuery.isPending);

  return <Modal title={title} onClose={onClose} size="l"><form className={styles.catalogForm} onSubmit={submit} noValidate>
    {showBanner ? <FormErrorBanner>{serverError ?? undefined}</FormErrorBanner> : null}
    {detailQuery.isError ? <FormErrorBanner>Не удалось загрузить полные данные записи. Закройте форму и попробуйте снова.</FormErrorBanner> : null}
    {type === 'agreements' ? null : <FormField label={type === 'responsibles' ? 'ФИО' : 'Название'} htmlFor={nameField.id} required error={nameField.error} errorId={nameField.errorId}><Input id={nameField.id} autoFocus maxLength={512} disabled={pending || detailLoading} aria-invalid={Boolean(nameField.error)} aria-describedby={nameField.error ? nameField.errorId : undefined} {...register('name')} /></FormField>}
    {type === 'universities' ? (() => { const meta = field('city'); return <FormField label="Город" htmlFor={meta.id} error={meta.error} errorId={meta.errorId} hint="Город указывается отдельно от региона."><Input id={meta.id} maxLength={256} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('city')} /></FormField>; })() : null}
    {type === 'vendors' ? <div className={styles.vendorContacts}><strong>Контакты вендора</strong>{vendorContactFields.map((contact, index) => <div className={styles.vendorContact} key={contact.id}><div className={styles.formGrid}><FormField label="Контактное лицо" htmlFor={`${id}-contact-name-${index}`} required error={errors.vendorContacts?.[index]?.fullName?.message} errorId={`${id}-contact-name-${index}-error`}><Input id={`${id}-contact-name-${index}`} maxLength={512} disabled={pending || detailLoading} {...register(`vendorContacts.${index}.fullName`)} /></FormField><FormField label="Email" htmlFor={`${id}-contact-email-${index}`} required error={errors.vendorContacts?.[index]?.email?.message} errorId={`${id}-contact-email-${index}-error`}><Input id={`${id}-contact-email-${index}`} type="email" maxLength={512} disabled={pending || detailLoading} {...register(`vendorContacts.${index}.email`)} /></FormField></div><div className={styles.formGrid}><FormField label="Телефон" htmlFor={`${id}-contact-phone-${index}`} errorId={`${id}-contact-phone-${index}-error`}><Input id={`${id}-contact-phone-${index}`} maxLength={64} disabled={pending || detailLoading} {...register(`vendorContacts.${index}.phone`)} /></FormField><FormField label="Способ связи" htmlFor={`${id}-contact-method-${index}`} errorId={`${id}-contact-method-${index}-error`}><Input id={`${id}-contact-method-${index}`} maxLength={256} disabled={pending || detailLoading} {...register(`vendorContacts.${index}.communicationMethod`)} /></FormField></div><Button type="button" variant="ghost" size="s" disabled={pending || detailLoading} onClick={() => removeVendorContact(index)}>Убрать контакт</Button></div>)}<Button type="button" variant="secondary" size="s" disabled={pending || detailLoading} onClick={() => addVendorContact({ fullName: '', email: '', phone: '', communicationMethod: '' })}>Добавить контакт</Button></div> : null}
    {type === 'products' ? <div className={styles.formGrid}>{(() => { const meta = field('vendorId'); return <FormField label="Вендор" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('vendorId')}><option value="">Выберите вендора</option>{references.vendors.map((vendor) => <option value={vendor.id} key={vendor.id}>{vendor.name}</option>)}</Select></FormField>; })()}{(() => { const meta = field('programId'); return <FormField label="ИТ-программа" htmlFor={meta.id} error={meta.error} errorId={meta.errorId} hint="Программа определяет направление продукта."><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('programId')}><option value="">Без программы</option>{references.programs.map((program) => <option value={program.id} key={program.id}>{program.name}</option>)}</Select></FormField>; })()}{(() => { const meta = field('version'); return <FormField label="Версия" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Input id={meta.id} maxLength={128} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('version')} /></FormField>; })()}</div> : null}
    {type === 'directions' ? (() => { const meta = field('code'); return <FormField label="Код" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Input id={meta.id} maxLength={64} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('code')} /></FormField>; })() : null}
    {type === 'programs' ? <>{(() => { const meta = field('directionId'); return <FormField label="Направление" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('directionId')}><option value="">Выберите направление</option>{references.directions.map((direction) => <option value={direction.id} key={direction.id}>{direction.description ? `${direction.name} (${direction.description})` : direction.name}</option>)}</Select></FormField>; })()}{(() => { const meta = field('description'); return <FormField label="Описание" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><TextArea id={meta.id} rows={3} maxLength={4000} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('description')} /></FormField>; })()}</> : null}
    {type === 'responsibles' ? <><div className={styles.formGrid}>{(() => { const meta = field('email'); return <FormField label="Email" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Input id={meta.id} type="email" maxLength={512} disabled={pending || detailLoading} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('email')} /></FormField>; })()}{(() => { const meta = field('phone'); return <FormField label="Телефон" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Input id={meta.id} maxLength={64} disabled={pending || detailLoading} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('phone')} /></FormField>; })()}</div>{(() => { const meta = field('role'); return <FormField label="Роль" htmlFor={meta.id} error={meta.error} errorId={meta.errorId} hint="Укажите должность или роль ответственного."><Input id={meta.id} maxLength={256} disabled={pending || detailLoading} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('role')} /></FormField>; })()}<Controller control={control} name="universityIds" render={({ field: universityField }) => <div className={styles.multiField}><span>Доступные ВУЗы</span><MultiSelect label="ВУЗы" options={references.universities} values={universityField.value} onChange={universityField.onChange} searchable loading={detailLoading} disabled={pending || detailLoading || detailQuery.isError} /></div>} /></> : null}
    {type === 'agreements' && kind === 'contracts' ? <>{(() => { const meta = field('universityId'); return <FormField label="ВУЗ" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Select id={meta.id} autoFocus disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('universityId')}><option value="">Выберите ВУЗ</option>{references.universities.map((option) => <option value={option.id} key={option.id}>{option.name}</option>)}</Select></FormField>; })()}{(() => { const meta = field('contractNumber'); return <FormField label="Номер договора" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Input id={meta.id} maxLength={64} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('contractNumber')} /></FormField>; })()}{(() => { const meta = field('productId'); return <FormField label="ИТ-продукт" htmlFor={meta.id} error={meta.error} errorId={meta.errorId} hint="Продукт привязывает договор к вендору."><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('productId')}><option value="">Без продукта</option>{references.products.map((option) => <option value={option.id} key={option.id}>{option.description ? `${option.name} (${option.description})` : option.name}</option>)}</Select></FormField>; })()}<div className={styles.formGrid}>{(() => { const meta = field('signedAt'); return <FormField label="Дата подписания" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Input id={meta.id} type="date" disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('signedAt')} /></FormField>; })()}{(() => { const meta = field('expiresAt'); return <FormField label="Дата окончания" htmlFor={meta.id} error={meta.error} errorId={meta.errorId} hint="Пусто — бессрочный договор."><Input id={meta.id} type="date" disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('expiresAt')} /></FormField>; })()}</div><div className={styles.formGrid}>{(() => { const meta = field('statusRaw'); return <FormField label="Статус договора" htmlFor={meta.id} error={meta.error} errorId={meta.errorId} hint="Итоговый статус (действует/истёк) рассчитывается автоматически."><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('statusRaw')}><option value="draft">Черновик</option><option value="signed">Подписан</option><option value="terminated">Расторгнут</option></Select></FormField>; })()}{(() => { const meta = field('transferStatus'); return <FormField label="Статус передачи" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('transferStatus')}><option value="pending">Ожидает</option><option value="transferred">Передан</option><option value="accepted">Принят</option><option value="rejected">Отклонён</option></Select></FormField>; })()}</div>{(() => { const meta = field('comment'); return <FormField label="Комментарий" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><TextArea id={meta.id} rows={3} maxLength={4000} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('comment')} /></FormField>; })()}</> : null}
    {type === 'agreements' && kind === 'licenses' ? <>{(() => { const meta = field('universityId'); return <FormField label="ВУЗ" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Select id={meta.id} autoFocus disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('universityId')}><option value="">Выберите ВУЗ</option>{references.universities.map((option) => <option value={option.id} key={option.id}>{option.name}</option>)}</Select></FormField>; })()}{(() => { const meta = field('licenseNumber'); return <FormField label="Номер лицензии" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Input id={meta.id} maxLength={64} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('licenseNumber')} /></FormField>; })()}<div className={styles.formGrid}>{(() => { const meta = field('productId'); return <FormField label="ИТ-продукт" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('productId')}><option value="">Выберите продукт</option>{references.products.map((option) => <option value={option.id} key={option.id}>{option.description ? `${option.name} (${option.description})` : option.name}</option>)}</Select></FormField>; })()}{(() => { const meta = field('contractId'); return <FormField label="Договор" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('contractId')}><option value="">Без договора</option>{references.contracts.map((option) => <option value={option.id} key={option.id}>{option.description ? `${option.name} — ${option.description}` : option.name}</option>)}</Select></FormField>; })()}</div><div className={styles.formGrid}>{(() => { const meta = field('programId'); return <FormField label="ИТ-программа" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('programId')}><option value="">Без программы</option>{references.programs.map((option) => <option value={option.id} key={option.id}>{option.name}</option>)}</Select></FormField>; })()}{(() => { const meta = field('directionId'); return <FormField label="Направление" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('directionId')}><option value="">Без направления</option>{references.directions.map((option) => <option value={option.id} key={option.id}>{option.description ? `${option.name} (${option.description})` : option.name}</option>)}</Select></FormField>; })()}</div><div className={styles.formGrid}>{(() => { const meta = field('signedAt'); return <FormField label="Дата подписания" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId}><Input id={meta.id} type="date" disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('signedAt')} /></FormField>; })()}{(() => { const meta = field('expiresAt'); return <FormField label="Дата окончания" htmlFor={meta.id} required error={meta.error} errorId={meta.errorId} hint="У лицензии срок действия обязателен."><Input id={meta.id} type="date" disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('expiresAt')} /></FormField>; })()}{(() => { const meta = field('transferStatus'); return <FormField label="Статус передачи" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><Select id={meta.id} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('transferStatus')}><option value="pending">Ожидает</option><option value="transferred">Передан</option><option value="accepted">Принят</option><option value="rejected">Отклонён</option></Select></FormField>; })()}</div>{(() => { const meta = field('comment'); return <FormField label="Комментарий" htmlFor={meta.id} error={meta.error} errorId={meta.errorId}><TextArea id={meta.id} rows={3} maxLength={4000} disabled={pending} aria-invalid={Boolean(meta.error)} aria-describedby={meta.error ? meta.errorId : undefined} {...register('comment')} /></FormField>; })()}</> : null}
    <div className={styles.modalActions}><Button type="button" variant="ghost" disabled={pending} onClick={onClose}>Отмена</Button><Button type="submit" variant="primary" loading={pending} disabled={pending || detailLoading || detailQuery.isError}>{item ? 'Сохранить' : 'Добавить'}</Button></div>
  </form></Modal>;
}
