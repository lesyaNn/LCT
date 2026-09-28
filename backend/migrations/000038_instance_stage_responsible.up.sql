ALTER TABLE instance_stages ADD COLUMN responsible_id UUID;
ALTER TABLE instance_stages
    ADD CONSTRAINT fk_instance_stages_responsible_id_responsibles
    FOREIGN KEY (responsible_id) REFERENCES responsibles (id) ON DELETE SET NULL;
