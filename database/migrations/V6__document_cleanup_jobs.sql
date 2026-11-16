-- V5 is reserved by the existing auth-enhancements password reset work.
-- No foreign key: cleanup must survive deletion of document/lesson metadata.
CREATE TABLE document_cleanup_jobs (
    storage_key VARCHAR(500) NOT NULL PRIMARY KEY,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
