CREATE TABLE notes (
    id UUID PRIMARY KEY,
    owner_sub TEXT NOT NULL,
    title VARCHAR(300) NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_notes_note_revision CHECK (revision >= 0)
);
CREATE INDEX ix_notes_owner_updated ON notes (owner_sub, updated_at);
