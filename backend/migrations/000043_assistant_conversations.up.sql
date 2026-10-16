-- Local assistant history, independent of all workflow/catalog migrations.
CREATE TABLE assistant_conversations (
    id UUID PRIMARY KEY,
    owner_sub TEXT NOT NULL,
    role VARCHAR(16) NOT NULL,
    title VARCHAR(120) NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_assistant_conversations_assistant_role
        CHECK (role IN ('user', 'manager', 'admin')),
    CONSTRAINT ck_assistant_conversations_assistant_revision CHECK (revision >= 0)
);
CREATE INDEX ix_assistant_conversations_owner_updated
    ON assistant_conversations (owner_sub, updated_at);

CREATE TABLE assistant_turns (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES assistant_conversations(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    basis VARCHAR(24) NOT NULL,
    sources JSONB NOT NULL,
    knowledge_version VARCHAR(64) NOT NULL,
    retrieval_mode VARCHAR(16) NOT NULL,
    model VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_assistant_turns_assistant_turn_position CHECK (position > 0),
    CONSTRAINT ck_assistant_turns_assistant_basis
        CHECK (basis IN ('documentation', 'inference', 'insufficient'))
);
CREATE UNIQUE INDEX uq_assistant_turns_position ON assistant_turns (conversation_id, position);
