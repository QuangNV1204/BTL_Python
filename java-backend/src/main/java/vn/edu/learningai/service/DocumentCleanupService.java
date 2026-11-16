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

    public void afterRollback(String key) {
        requireTransaction();
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCompletion(int status) {
                if (status == STATUS_ROLLED_BACK) {
                    try {
                        storage.delete(key);
                    } catch (RuntimeException failure) {
                        log.error("Uploaded document cleanup failed after rollback", failure);
                        var tx = new TransactionTemplate(transactionManager);
                        tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
                        tx.executeWithoutResult(s -> jdbc.sql(
                            "INSERT IGNORE INTO document_cleanup_jobs(storage_key) VALUES(:key)")
                            .param("key", key).update());
                    }
                }
            }
        });
    }

    private void requireTransaction() {
        if (!TransactionSynchronizationManager.isActualTransactionActive()
                || !TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException("Document cleanup requires a database transaction");
        }
    }

    @Scheduled(fixedDelayString = "${app.storage.cleanup-delay-ms:60000}")
    public void retryPending() {
        for (String key : jdbc.sql("SELECT storage_key FROM document_cleanup_jobs ORDER BY created_at,storage_key LIMIT 100")
                .query(String.class).list()) {
            cleanup(key);
        }
    }

    private void cleanup(String key) {
        try {
            var tx = new TransactionTemplate(transactionManager);
            tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            tx.executeWithoutResult(status -> {
                // Lock before deleting the file: overlapping retry/callbacks serialize.
                var job = jdbc.sql("SELECT storage_key FROM document_cleanup_jobs WHERE storage_key=:key FOR UPDATE")
                    .param("key", key).query(String.class).optional();
                if (job.isEmpty()) return;
                storage.delete(key); // UUID keys are never reused; deletion is idempotent.
                jdbc.sql("DELETE FROM document_cleanup_jobs WHERE storage_key=:key").param("key", key).update();
            });
        } catch (RuntimeException failure) {
            // Metadata deletion already committed. Keep the durable job for retry.
            log.error("Document cleanup failed; durable job retained for retry", failure);
        }
    }
}
