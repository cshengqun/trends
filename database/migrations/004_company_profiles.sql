CREATE TABLE company_profiles (
    entity_id text PRIMARY KEY REFERENCES entities (id),
    business_model text NOT NULL,
    target_users text NOT NULL,
    source_label text NOT NULL,
    source_url text NOT NULL
);
