-- SQL migration 000013: tasks.priority (P2-07-02).
--
-- Source of truth for: tasks.priority + index.
-- Replaces Alembic d4e707020001 (same DDL, same names).
--
-- Notes:
-- * priority VARCHAR(32) NOT NULL DEFAULT 'normal' (normal/critical/high? —
--   контракт P2-07-02: critical = -8, остальное = -4; существующие строки
--   получают 'normal' через DEFAULT).
-- * Композитный индекс (instance_id, priority) для подсчёта просрочек
--   по приоритетам без scan всей таблицы задач инстанса.

ALTER TABLE tasks ADD COLUMN priority VARCHAR(32) NOT NULL DEFAULT 'normal';
CREATE INDEX ix_tasks_instance_priority ON tasks USING btree (instance_id, priority);
