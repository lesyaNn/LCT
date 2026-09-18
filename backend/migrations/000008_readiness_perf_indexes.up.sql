-- SQL migration 000008: teacher readiness composite indexes.
--
-- Replaces Alembic 7f3a1c9e2b06 (current head).
-- Passport teacher scalars filter teacher_id + expires_at range per loop;
-- composites turn Bitmap Heap Scan + Filter into Index (Only) Scan.
-- Verified BEFORE/AFTER via EXPLAIN (P1-10-02): no other indexes added here.

CREATE INDEX ix_teacher_certificates_teacher_expires ON teacher_certificates USING btree (teacher_id, expires_at);
CREATE INDEX ix_teacher_qualifications_teacher_expires ON teacher_qualifications USING btree (teacher_id, expires_at);
