CREATE TABLE notifications (
    id UUID CONSTRAINT pk_notifications PRIMARY KEY,
    recipient_user_id VARCHAR(256) NOT NULL,
    event_key VARCHAR(256) NOT NULL,
    type VARCHAR(64) NOT NULL,
    priority VARCHAR(16) NOT NULL,
    title VARCHAR(256) NOT NULL,
    message TEXT NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(64) NOT NULL,
    university_id UUID CONSTRAINT fk_notifications_university_id_universities REFERENCES universities(id) ON DELETE SET NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at TIMESTAMPTZ,
    CONSTRAINT uq_notifications_recipient_event UNIQUE (recipient_user_id, event_key)
);
CREATE INDEX ix_notifications_recipient_created ON notifications (recipient_user_id, created_at);
CREATE INDEX ix_notifications_recipient_unread ON notifications (recipient_user_id, is_read);
