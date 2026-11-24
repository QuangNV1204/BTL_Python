package vn.edu.learningai.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@EnableScheduling
@RequiredArgsConstructor
@Slf4j
public class DocumentCleanupService {
    private final JdbcClient jdbc;
    private final DocumentStorage storage;
    private final PlatformTransactionManager transactionManager;

    public void afterCommit(String key) {
        requireTransaction();
        jdbc.sql("INSERT IGNORE INTO document_cleanup_jobs(storage_key) VALUES(:key)")
            .param("key", key).update();
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() { cleanup(key); }
        });
    }

    public void stageUpload(String key) {
        requireTransaction();
        var tx = new TransactionTemplate(transactionManager);
        tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        tx.executeWithoutResult(s -> jdbc.sql(
            "INSERT INTO document_cleanup_jobs(storage_key,job_type) VALUES(:key,'STAGING')").param("key", key).update());
        var job = jdbc.sql("SELECT storage_key FROM document_cleanup_jobs WHERE storage_key=:key FOR UPDATE")
            .param("key", key).query(String.class).optional();
        if (job.isEmpty()) throw new IllegalStateException("Upload staging was reclaimed; retry upload");
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCompletion(int status) {
                if (status == STATUS_ROLLED_BACK) cleanup(key);
            }
        });
    }

    public void adoptUpload(String key) {
        requireTransaction();
        jdbc.sql("DELETE FROM document_cleanup_jobs WHERE storage_key=:key").param("key", key).update();
    }

    private void requireTransaction() {
        if (!TransactionSynchronizationManager.isActualTransactionActive()
                || !TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException("Document cleanup requires a database transaction");
        }
    }

    @Scheduled(fixedDelayString = "${app.storage.cleanup-delay-ms:60000}")
    public void retryPending() {
        for (String key : jdbc.sql("SELECT storage_key FROM document_cleanup_jobs ORDER BY checked_at,storage_key LIMIT 100")
                .query(String.class).list()) {
            cleanup(key);
        }
    }

    private void cleanup(String key) {
        try {
            var tx = new TransactionTemplate(transactionManager);
            tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            tx.executeWithoutResult(status -> {
                var job = jdbc.sql("SELECT job_type FROM document_cleanup_jobs WHERE storage_key=:key FOR UPDATE SKIP LOCKED")
                    .param("key", key).query(String.class).optional();
                if (job.isEmpty()) return;
                boolean adopted = jdbc.sql("SELECT EXISTS(SELECT 1 FROM lesson_documents WHERE storage_key=:key)")
                    .param("key", key).query(Boolean.class).single();
                if (!adopted) storage.delete(key); 
                if (adopted || "DELETE".equals(job.get())) {
                    jdbc.sql("DELETE FROM document_cleanup_jobs WHERE storage_key=:key").param("key", key).update();
                } else {
                    jdbc.sql("UPDATE document_cleanup_jobs SET checked_at=UTC_TIMESTAMP(6) WHERE storage_key=:key")
                        .param("key", key).update();
                }
            });
        } catch (RuntimeException failure) {
            log.error("Document cleanup failed; durable job retained for retry", failure);
        }
    }
}
