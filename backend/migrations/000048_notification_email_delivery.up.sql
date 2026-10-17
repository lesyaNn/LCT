CREATE TABLE notification_deliveries (
    id UUID CONSTRAINT pk_notification_deliveries PRIMARY KEY,
    notification_id UUID NOT NULL CONSTRAINT fk_notification_deliveries_notification REFERENCES notifications(id) ON DELETE CASCADE,
    channel VARCHAR(16) NOT NULL CONSTRAINT ck_notification_deliveries_channel CHECK (channel = 'email'),
    recipient VARCHAR(512) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending' CONSTRAINT ck_notification_deliveries_status CHECK (status IN ('pending', 'processing', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CONSTRAINT ck_notification_deliveries_attempts CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_attempt_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    last_error TEXT,
    claim_token UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_notification_deliveries_channel UNIQUE (notification_id, channel)
);
CREATE INDEX ix_notification_deliveries_due ON notification_deliveries (status, next_attempt_at);
