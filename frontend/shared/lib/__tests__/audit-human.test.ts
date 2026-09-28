/** Frontend unit tests for the human-readable audit layer.
 *
 * Run: `npm run test:audit` (compiles this + audit-human/formatters with
 * `tsc --noCheck` into a temp dir and executes `node --test`).
 */
import { describe, it } from 'node:test';
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  AUDIT_ACTION_GROUP_OPTIONS,
  AUDIT_SECTION_OPTIONS,
  auditActorName,
  formatAuditFieldLabel,
  formatAuditFieldValue,
  getAuditEntityLabel,
  getAuditRoleLabel,
  isUuidLike,
  summarizeAuditEvent,
  universityDisplayName,
} from '../audit-human';
import type { AuditEvent } from '../audit-repository';

const UUID_RE = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/;
const TECHNICAL = [
  'Admin config', 'Config', 'workflow_instance', 'workflow_comment', 'external_sync',
  'template_id', 'program_id', 'product_id', 'responsible_id', 'direction_id',
  'vendor_id', 'stage_id', 'instance_id', 'keycloak_sub', 'author_keycloak_sub',
  'order_index', 'is_active', 'is_required', 'sla_days',
];

function baseEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    id: 'test-1',
    occurredAt: '2026-09-26T17:32:00.000Z',
    user: { id: 'user-1', name: 'Demo Admin' },
    role: 'admin',
    action: 'UPDATE',
    entity: { id: 'entity-1', type: 'university', label: '' },
    university: { id: 'uni-1', name: 'МТУСИ' },
    ...overrides,
  };
}

function assertHuman(...texts: Array<string | null>): void {
  for (const text of texts) {
    if (!text) continue;
    assert.ok(!UUID_RE.test(text), `UUID leaked: ${text}`);
  }
  const joined = texts.filter(Boolean).join('\n');
  for (const word of TECHNICAL) {
    assert.ok(!joined.includes(word), `technical token leaked: ${word} in ${joined}`);
  }
}

describe('audit-human: action/entity/role labels', () => {
  it('translates entity types to Russian, unknown becomes neutral', () => {
    assert.equal(getAuditEntityLabel('university'), 'ВУЗ');
    assert.equal(getAuditEntityLabel('workflow_stage'), 'Этап Workflow');
    assert.equal(getAuditEntityLabel('document'), 'Файл');
    assert.equal(getAuditEntityLabel('config'), 'Настройки');
    assert.equal(getAuditEntityLabel('something_new'), 'Системный объект');
  });

  it('translates roles', () => {
    assert.equal(getAuditRoleLabel('admin'), 'Администратор');
    assert.equal(getAuditRoleLabel('manager'), 'Менеджер');
    assert.equal(getAuditRoleLabel(undefined), '—');
  });

  it('actor fallback is human, never system/uuid', () => {
    assert.equal(auditActorName(baseEvent()), 'Demo Admin');
    assert.equal(auditActorName(baseEvent({ user: { id: 'x', name: 'system' } })), 'Система');
    assert.equal(auditActorName(baseEvent({ user: { id: 'x', name: '' } })), 'Пользователь (имя недоступно)');
    assert.equal(auditActorName(baseEvent({ user: { id: '585d5f6e-58f4-4072-a2c5-17e3e8a61117', name: '585d5f6e-58f4-4072-a2c5-17e3e8a61117' } })), 'Пользователь (имя недоступно)');
    assert.equal(auditActorName(baseEvent({ user: { id: 'keycloak-sub', name: 'keycloak-sub' } })), 'Пользователь (имя недоступно)');
  });

  it('isUuidLike detects UUID-shaped strings', () => {
    assert.equal(isUuidLike('585d5f6e-58f4-4072-a2c5-17e3e8a61117'), true);
    assert.equal(isUuidLike('МТУСИ'), false);
    assert.equal(isUuidLike(''), false);
    assert.equal(isUuidLike(null), false);
  });
});

describe('audit-human: university display guard', () => {
  const DELETED_ID = '585d5f6e-58f4-4072-a2c5-17e3e8a61117';

  it('prefers the human university name', () => {
    assert.equal(universityDisplayName(baseEvent()), 'МТУСИ');
  });

  it('deleted university: historic object name from presentation, never UUID', () => {
    const event = baseEvent({
      entity: { id: DELETED_ID, type: 'university', label: 'ВУЗ' },
      university: { id: DELETED_ID, name: '—' },
      presentation: {
        title: 'Удалил ВУЗ «Удалённый ВУЗ»', section: 'ВУЗы', object_name: 'Удалённый ВУЗ',
        changes: [], note: null, actor_name: 'Demo Admin', actor_role: 'admin',
      },
    });
    assert.equal(universityDisplayName(event), 'Удалённый ВУЗ');
    assert.ok(!UUID_RE.test(universityDisplayName(event)));
  });

  it('nothing resolvable: empty string so callers render the section', () => {
    const event = baseEvent({
      entity: { id: DELETED_ID, type: 'university', label: 'ВУЗ' },
      university: { id: DELETED_ID, name: '—' },
      presentation: null,
    });
    assert.equal(universityDisplayName(event), '');
  });

  it('UUID-like university name never passes through', () => {
    const event = baseEvent({ university: { id: DELETED_ID, name: DELETED_ID } });
    assert.equal(universityDisplayName(event), '');
  });
});

describe('audit-human: UUID invariant across user strings', () => {
  const DELETED_ID = '585d5f6e-58f4-4072-a2c5-17e3e8a61117';
  const cases: AuditEvent[] = [
    baseEvent({ action: 'CREATE', oldValues: undefined, newValues: { name: 'МТУСИ', city: 'Москва' } }),
    baseEvent({ action: 'DELETE', entity: { id: DELETED_ID, type: 'university', label: 'ВУЗ' }, university: { id: DELETED_ID, name: '—' }, oldValues: { name: 'МТУСИ', city: 'Москва' }, newValues: undefined }),
    baseEvent({ action: 'ADMIN_CONFIG', entity: { id: 's1', type: 'workflow_stage', label: '' }, university: { id: '', name: '—' }, oldValues: null, newValues: { template_id: DELETED_ID, name: 'Этап', order_index: 1, is_active: true } }),
    baseEvent({ action: 'WORKFLOW_TRANSITION', entity: { id: 'i1', type: 'workflow_instance', label: '' }, oldValues: { stage_id: DELETED_ID, stage_name: 'A' }, newValues: { stage_id: DELETED_ID, stage_name: 'B', comment: 'ok' } }),
    baseEvent({ action: 'ASSIGN_RESPONSIBLE', entity: { id: 'r1', type: 'responsible', label: '' }, oldValues: { responsible_id: DELETED_ID }, newValues: { responsible_id: DELETED_ID, responsible_name: 'Иван Петров' } }),
    baseEvent({ action: 'SOMETHING_NEW', entity: { id: 'x', type: 'my_type', label: '' }, oldValues: { some_id: DELETED_ID }, newValues: { some_id: DELETED_ID } }),
  ];
  it('title/section/object/changes/note/university contain no UUID', () => {
    for (const event of cases) {
      const summary = summarizeAuditEvent(event);
      const texts = [
        summary.title, summary.section, summary.objectName, summary.note,
        universityDisplayName(event), summary.actorName,
        ...summary.changes.flatMap((row) => [row.label, row.old, row.next]),
      ];
      for (const text of texts) {
        if (!text) continue;
        assert.ok(!UUID_RE.test(text), `UUID leaked in ${event.action}/${event.entity.type}: ${text}`);
      }
    }
  });
});

describe('audit-human: field formatters', () => {
  it('labels fields in Russian', () => {
    assert.equal(formatAuditFieldLabel('order_index'), 'Порядок этапа');
    assert.equal(formatAuditFieldLabel('sla_days'), 'Срок выполнения');
    assert.equal(formatAuditFieldLabel('meeting_type'), 'Формат встречи');
    assert.equal(formatAuditFieldLabel('original_filename'), 'Имя файла');
  });

  it('formats booleans contextually, never true/false', () => {
    assert.equal(formatAuditFieldValue('is_active', true), 'Включён');
    assert.equal(formatAuditFieldValue('is_active', false), 'Выключен');
    assert.equal(formatAuditFieldValue('is_required', false), 'Необязательный');
    assert.equal(formatAuditFieldValue('is_primary', true), 'Основной');
  });

  it('formats enums in Russian', () => {
    assert.equal(formatAuditFieldValue('meeting_type', 'online'), 'Онлайн');
    assert.equal(formatAuditFieldValue('meeting_type', 'email'), 'Электронная почта');
    assert.equal(formatAuditFieldValue('status', 'planned'), 'Запланирована');
  });

  it('formats dates and file sizes', () => {
    assert.equal(formatAuditFieldValue('meeting_at', '2026-09-26T15:00:00+03:00'), '26.09.2026, 15:00');
    assert.equal(formatAuditFieldValue('next_action_due', '2026-09-26'), '26.09.2026');
    assert.equal(formatAuditFieldValue('file_size', 102400), '100 КБ');
    assert.equal(formatAuditFieldValue('sla_days', 7), '7 дней');
  });

  it('never returns raw UUIDs', () => {
    assert.equal(formatAuditFieldValue('template_id', '30d06bca-af1a-4483-a835-5b7121b20ac2'), '');
  });
});

describe('audit-human: summarize', () => {
  it('university update with было → стало', () => {
    const summary = summarizeAuditEvent(baseEvent({
      action: 'UPDATE',
      oldValues: { name: 'МТУСИ', city: 'Москва' },
      newValues: { name: 'МТУСИ', city: 'Санкт-Петербург' },
    }));
    assert.equal(summary.title, 'Изменил ВУЗ «МТУСИ»');
    assert.equal(summary.changes[0].label, 'Город');
    assert.equal(summary.changes[0].next, 'Санкт-Петербург');
    assertHuman(summary.title, summary.section);
  });

  it('old stage payload (template_id/order_index) stays human', () => {
    const summary = summarizeAuditEvent(baseEvent({
      action: 'ADMIN_CONFIG',
      entity: { id: 's1', type: 'workflow_stage', label: '' },
      oldValues: { name: 'Согласование', order_index: 2, is_active: true, is_required: false, sla_days: 5 },
      newValues: { name: 'Согласование', order_index: 3, is_active: true, is_required: true, sla_days: 7 },
    }));
    assert.equal(summary.title, 'Изменил этап «Согласование»');
    const byLabel = new Map(summary.changes.map((row) => [row.label, row]));
    assert.equal(byLabel.get('Порядок этапа')?.next, '3');
    assert.equal(byLabel.get('Обязательный этап')?.next, 'Обязательный');
    assert.equal(byLabel.get('Срок выполнения')?.next, '7 дней');
    assertHuman(summary.title, summary.section, ...summary.changes.flatMap((row) => [row.label, row.old, row.next]));
  });

  it('workflow transition sentence with comment', () => {
    const summary = summarizeAuditEvent(baseEvent({
      action: 'WORKFLOW_TRANSITION',
      entity: { id: 'i1', type: 'workflow_instance', label: '' },
      oldValues: { stage_name: 'Подготовка' },
      newValues: { stage_name: 'Запуск', comment: 'Документы согласованы' },
    }));
    assert.equal(summary.title, 'Перевёл «МТУСИ» с этапа «Подготовка» на этап «Запуск»');
    assertHuman(summary.title);
  });

  it('user role change', () => {
    const summary = summarizeAuditEvent(baseEvent({
      action: 'ADMIN_CONFIG',
      entity: { id: 'u1', type: 'config', label: '' },
      oldValues: { kind: 'role', value: 'manager', target_name: 'Иван Петров' },
      newValues: { kind: 'role', value: 'admin', target_name: 'Иван Петров' },
    }));
    assert.equal(summary.title, 'Изменил роль пользователя «Иван Петров»');
    assert.equal(summary.changes[0].next, 'Администратор');
    assertHuman(summary.title);
  });

  it('assign/unassign responsible', () => {
    const assigned = summarizeAuditEvent(baseEvent({
      action: 'ASSIGN_RESPONSIBLE',
      entity: { id: 'r1', type: 'responsible', label: '' },
      oldValues: { responsible_id: null },
      newValues: { responsible_id: 'some-id', responsible_name: 'Иван Петров' },
    }));
    assert.ok(assigned.title.includes('Иван Петров'));
    const unassigned = summarizeAuditEvent(baseEvent({
      action: 'ASSIGN_RESPONSIBLE',
      entity: { id: 'r1', type: 'responsible', label: '' },
      oldValues: { responsible_id: 'some-id', responsible_name: 'Анна Смирнова' },
      newValues: { responsible_id: null },
    }));
    assert.ok(unassigned.title.includes('Анна Смирнова'));
    assertHuman(assigned.title, unassigned.title);
  });

  it('server presentation wins over local compute', () => {
    const summary = summarizeAuditEvent(baseEvent({
      presentation: {
        title: 'Перевёл «МТУСИ» с этапа «Подготовка» на этап «Запуск»',
        section: 'Workflow',
        object_name: 'МТУСИ',
        changes: [{ field: 'stage_name', label: 'Этап', old: 'Подготовка', new: 'Запуск' }],
        note: null,
        actor_name: 'Иван Петров',
        actor_role: 'manager',
      },
    }));
    assert.equal(summary.title, 'Перевёл «МТУСИ» с этапа «Подготовка» на этап «Запуск»');
    assert.equal(summary.actorName, 'Иван Петров');
    assert.equal(summary.changes[0].next, 'Запуск');
  });

  it('unknown event degrades to neutral fallback', () => {
    const summary = summarizeAuditEvent(baseEvent({
      action: 'SOMETHING_NEW',
      entity: { id: 'x', type: 'my_custom_thing', label: '' },
      oldValues: { weird_field: 'x' },
      newValues: { weird_field: 'y' },
    }));
    assert.equal(summary.title, 'Изменение данных');
    assertHuman(summary.title, summary.section);
  });

  it('workflow attachment upload uses the canonical payload and keeps the actor', () => {
    const summary = summarizeAuditEvent(baseEvent({
      action: 'CREATE',
      entity: { id: 'file-1', type: 'document', label: '' },
      user: { id: 'author-1', name: 'Анна Морозова' },
      newValues: { audit_object_type: 'workflow_attachment', instance_id: 'instance-1', original_filename: 'Договор.pdf', file_size: 2048 },
      presentation: { title: 'Системное изменение', section: 'Система', actor_name: 'Системное действие' },
    }));
    assert.equal(summary.title, 'Загрузил файл «Договор.pdf»');
    assert.equal(summary.actorName, 'Анна Морозова');
    assert.equal(summary.section, 'Файлы');
  });

  it('deleted entity uses fallback, not UUID', () => {
    const summary = summarizeAuditEvent(baseEvent({
      action: 'DELETE',
      entity: { id: '30d06bca-af1a-4483-a835-5b7121b20ac2', type: 'program', label: '' },
      university: { id: '', name: '—' },
      oldValues: { direction_id: '30d06bca-af1a-4483-a835-5b7121b20ac2' },
    }));
    assert.ok(!UUID_RE.test(summary.title));
    assertHuman(summary.title, summary.section);
  });
});

describe('audit-human: filters', () => {
  it('action groups cover all real backend actions', () => {
    const covered = new Set(AUDIT_ACTION_GROUP_OPTIONS.flatMap((group) => group.actions));
    for (const action of ['CREATE', 'UPDATE', 'DELETE', 'WORKFLOW_TRANSITION', 'ASSIGN_RESPONSIBLE', 'IMPORT', 'REPORT_GENERATE', 'ADMIN_CONFIG']) {
      assert.ok(covered.has(action), `action not covered: ${action}`);
    }
  });

  it('sections avoid the «Тип сущности» term', () => {
    const labels = AUDIT_SECTION_OPTIONS.map((section) => section.label).join(' ');
    assert.ok(!labels.includes('Тип сущности'));
    assert.ok(!labels.includes('Config'));
  });
});

describe('audit page: responsive regression', () => {
  const root = process.cwd();
  it('table has 5 human columns, no fixed 1180px layout', () => {
    const page = readFileSync(join(root, 'widgets/audit/audit-page.tsx'), 'utf-8');
    for (const header of ['Время', 'Кто', 'Что произошло', 'ВУЗ / Раздел', 'Изменение']) {
      assert.ok(page.includes(header), `missing column: ${header}`);
    }
    for (const banned of ['Старое значение', 'Новое значение', 'Min-width:1180', 'min-width: 1180px', '1180px']) {
      if (banned === '1180px') {
        const css = readFileSync(join(root, 'widgets/audit/audit-page.module.css'), 'utf-8');
        assert.ok(!css.includes('1180px'), 'fixed 1180px layout still present');
      } else {
        assert.ok(!page.includes(banned), `legacy fragment still present: ${banned}`);
      }
    }
  });

  it('route title is user-friendly', () => {
    const route = readFileSync(join(root, 'app/(crm)/audit/page.tsx'), 'utf-8');
    assert.ok(route.includes('История изменений'));
  });

  it('no banned technical tokens in the human layer', () => {
    const source = readFileSync(join(root, 'shared/lib/audit-human.ts'), 'utf-8');
    for (const banned of ['Admin config', 'My type', 'Unknown', 'External sync']) {
      assert.ok(!source.includes(`'${banned}'`) && !source.includes(`"${banned}"`), `banned token: ${banned}`);
    }
  });
});
