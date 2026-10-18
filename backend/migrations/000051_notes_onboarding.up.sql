CREATE TABLE note_onboarding (
    owner_sub TEXT PRIMARY KEY,
    initialized_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
