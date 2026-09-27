-- SQL migration 000033: product -> program link (иерархия ТЗ).
--
-- Каноническая цепочка: направление <- программа <- продукт.
-- program_id NULL = продукт пока не привязан (отчёты в этом случае
-- показывают программу/направление только из прямых полей лицензии).
-- ON DELETE SET NULL: удаление программы не удаляет продукты.
-- Прямые product_directions (лист импорта "Продукт_Направление",
-- миграция 000028) не трогаем: это сырые данные импорта, а канон
-- для отчётов — цепочка через программу.

ALTER TABLE it_products
    ADD COLUMN program_id UUID REFERENCES it_programs(id) ON DELETE SET NULL;
CREATE INDEX ix_it_products_program_id ON it_products USING btree (program_id);
