ALTER TABLE document_cleanup_jobs
    ADD COLUMN job_type VARCHAR(16) NOT NULL DEFAULT 'DELETE',
    ADD COLUMN checked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ADD CONSTRAINT ck_document_cleanup_job_type CHECK (job_type IN ('DELETE', 'STAGING')),
    ADD INDEX idx_document_cleanup_retry (checked_at, storage_key);
