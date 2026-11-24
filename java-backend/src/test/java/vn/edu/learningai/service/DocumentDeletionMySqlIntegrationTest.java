package vn.edu.learningai.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.core.io.Resource;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest
@Import(DocumentDeletionMySqlIntegrationTest.StorageConfig.class)
@EnabledIfEnvironmentVariable(named="QUIZ_TEST_MYSQL_URL", matches="jdbc:mysql://[^/]+/learningai_quiz_test_documents(?:_[A-Za-z0-9]+)?(?:\\?.*)?")
@Sql("/test-fixtures.sql")
class DocumentDeletionMySqlIntegrationTest {
    @TempDir static Path root;
    @Autowired LessonService service;
    @Autowired DocumentCleanupService cleanup;
    @Autowired JdbcClient jdbc;
    @Autowired PlatformTransactionManager transactions;
    @Autowired TestStorage storage;

    @DynamicPropertySource static void properties(DynamicPropertyRegistry p) {
        p.add("spring.datasource.url", () -> System.getenv("QUIZ_TEST_MYSQL_URL"));
        p.add("spring.datasource.username", () -> System.getenv("QUIZ_TEST_MYSQL_USERNAME"));
        p.add("spring.datasource.password", () -> System.getenv().getOrDefault("QUIZ_TEST_MYSQL_PASSWORD", ""));
        p.add("jwt.jwt-signing-key", () -> Base64.getEncoder().encodeToString(new byte[32]));
        p.add("spring.jpa.show-sql", () -> false);
        p.add("app.storage.cleanup-delay-ms", () -> "3600000");
    }
    @TestConfiguration static class StorageConfig {
        @Bean @Primary TestStorage testStorage() { return new TestStorage(root); }
    }
    static class TestStorage implements DocumentStorage {
        final LocalDocumentStorage delegate;
        boolean fail;
        TestStorage(Path path) { delegate = new LocalDocumentStorage(path.toString()); }
        public String newKey(MultipartFile f) { return delegate.newKey(f); }
        public void store(String k, MultipartFile f) { delegate.store(k, f); }
        public Resource load(String k) { return delegate.load(k); }
        public void delete(String k) {
            if (fail) throw new IllegalStateException("injected storage failure");
            delegate.delete(k);
        }
    }
    private long upload() {
        return Long.parseLong(service.uploadDocument(1L,
            new MockMultipartFile("file", "test.txt", "text/plain", "test text".getBytes()), 2L).id().toString());
    }
    private String key(long id) {
        return jdbc.sql("SELECT storage_key FROM lesson_documents WHERE id=:id").param("id",id).query(String.class).single();
    }
    private long docs(long id) {
        return jdbc.sql("SELECT COUNT(*) FROM lesson_documents WHERE id=:id").param("id",id).query(Long.class).single();
    }
    @Test void failedStagingInsertNeverWritesFile() throws Exception {
        long before;
        try (var paths = Files.list(root)) { before = paths.count(); }
        jdbc.sql("CREATE TRIGGER test_staging_failure BEFORE INSERT ON document_cleanup_jobs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='injected staging DB failure'").update();
        try {
            assertThatThrownBy(this::upload).isInstanceOf(RuntimeException.class);
            try (var paths = Files.list(root)) { assertThat(paths.count()).isEqualTo(before); }
        } finally { jdbc.sql("DROP TRIGGER test_staging_failure").update(); }
    }

    @Test void abandonedUploadRecoversWithoutRollbackCallback() throws Exception {
        var file = new MockMultipartFile("file", "orphan.txt", "text/plain", "orphan".getBytes());
        String key = storage.newKey(file);
        jdbc.sql("INSERT INTO document_cleanup_jobs(storage_key,job_type) VALUES(:key,'STAGING')").param("key",key).update();
        storage.store(key,file);
        assertThat(root.resolve(key)).exists();
        var restarted = new DocumentCleanupService(jdbc,storage,transactions);
        restarted.retryPending();
        assertThat(root.resolve(key)).doesNotExist();
        assertThat(jdbc.sql("SELECT COUNT(*) FROM document_cleanup_jobs WHERE storage_key=:key")
            .param("key",key).query(Long.class).single()).isEqualTo(1);
        storage.store(key,file);
        restarted.retryPending();
        assertThat(root.resolve(key)).doesNotExist();
    }

    @Test void workerSkipsLiveUploadAndCommitAdoptsIt() throws Exception {
        var staged = new java.util.concurrent.CountDownLatch(1);
        var finish = new java.util.concurrent.CountDownLatch(1);
        var key = new java.util.concurrent.atomic.AtomicReference<String>();
        var pool = java.util.concurrent.Executors.newSingleThreadExecutor();
        try {
            var writer = pool.submit(() -> new TransactionTemplate(transactions).executeWithoutResult(s -> {
                long id = upload();
                key.set(key(id));
                staged.countDown();
                try {
                    if (!finish.await(10,java.util.concurrent.TimeUnit.SECONDS)) throw new IllegalStateException("test timeout");
                } catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new IllegalStateException(e); }
            }));
            assertThat(staged.await(10,java.util.concurrent.TimeUnit.SECONDS)).isTrue();
            org.junit.jupiter.api.Assertions.assertTimeoutPreemptively(java.time.Duration.ofSeconds(3), cleanup::retryPending);
            assertThat(root.resolve(key.get())).exists();
            finish.countDown();
            writer.get(10,java.util.concurrent.TimeUnit.SECONDS);
            cleanup.retryPending();
            assertThat(root.resolve(key.get())).exists();
            assertThat(jdbc.sql("SELECT COUNT(*) FROM document_cleanup_jobs WHERE storage_key=:key")
                .param("key",key.get()).query(Long.class).single()).isZero();
        } finally { finish.countDown(); pool.shutdownNow(); }
    }

    @Test void staleJobCannotDeleteCommittedDocument() {
        long id=upload(); String key=key(id);
        jdbc.sql("INSERT INTO document_cleanup_jobs(storage_key) VALUES(:key)").param("key",key).update();
        cleanup.retryPending();
        assertThat(root.resolve(key)).exists();
        assertThat(docs(id)).isEqualTo(1);
    }

    @Test void documentRollbackPreservesMetadataAndRealFile() {
        long id=upload(); String key=key(id);
        assertThatThrownBy(() -> new TransactionTemplate(transactions).executeWithoutResult(s -> {
            service.deleteDocument(id,2L);
            jdbc.sql("SELECT 1").query(Integer.class).single();
            throw new IllegalStateException("injected DB transaction failure");
        })).isInstanceOf(IllegalStateException.class);
        assertThat(docs(id)).isEqualTo(1);
        assertThat(root.resolve(key)).exists();
        assertThat(jdbc.sql("SELECT COUNT(*) FROM document_cleanup_jobs WHERE storage_key=:key").param("key",key).query(Long.class).single()).isZero();
    }
    @Test void lessonRollbackPreservesMetadataAndRealFile() {
        long id=upload(); String key=key(id);
        assertThatThrownBy(() -> new TransactionTemplate(transactions).executeWithoutResult(s -> {
            service.delete(1L,2L);
            throw new IllegalStateException("injected failure after lesson delete");
        })).isInstanceOf(IllegalStateException.class);
        assertThat(docs(id)).isEqualTo(1);
        assertThat(root.resolve(key)).exists();
        assertThat(jdbc.sql("SELECT COUNT(*) FROM lessons WHERE id=1").query(Long.class).single()).isEqualTo(1);
    }
    @Test void databaseDeleteFailurePreservesFileAndRollsBackJob() {
        long id=upload(); String key=key(id);
        jdbc.sql("CREATE TRIGGER test_document_delete_failure BEFORE DELETE ON lesson_documents FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='injected delete failure'").update();
        try {
            assertThatThrownBy(() -> service.deleteDocument(id,2L)).isInstanceOf(RuntimeException.class);
            assertThat(docs(id)).isEqualTo(1);
            assertThat(root.resolve(key)).exists();
            assertThat(jdbc.sql("SELECT COUNT(*) FROM document_cleanup_jobs WHERE storage_key=:key")
                .param("key",key).query(Long.class).single()).isZero();
        } finally {
            jdbc.sql("DROP TRIGGER test_document_delete_failure").update();
        }
    }
    @Test void failedStorageCleanupIsDurableAndRetried() {
        long id=upload(); String key=key(id);
        storage.fail=true;
        try {
            service.deleteDocument(id,2L);
            assertThat(docs(id)).isZero();
            assertThat(root.resolve(key)).exists();
            assertThat(jdbc.sql("SELECT COUNT(*) FROM document_cleanup_jobs WHERE storage_key=:key").param("key",key).query(Long.class).single()).isEqualTo(1);
        } finally { storage.fail=false; }
        cleanup.retryPending();
        assertThat(root.resolve(key)).doesNotExist();
        assertThat(jdbc.sql("SELECT COUNT(*) FROM document_cleanup_jobs WHERE storage_key=:key").param("key",key).query(Long.class).single()).isZero();
    }
    @Test void uploadRollbackRemovesNewFile() throws Exception {
        long before;
        try(var paths=Files.list(root)) { before=paths.count(); }
        assertThatThrownBy(() -> new TransactionTemplate(transactions).executeWithoutResult(s -> {
            upload(); throw new IllegalStateException("injected failure after upload");
        })).isInstanceOf(IllegalStateException.class);
        try(var paths=Files.list(root)) { assertThat(paths.count()).isEqualTo(before); }
    }
    @Test void unauthorizedTeacherCannotDeleteFile() {
        long id=upload(); String key=key(id);
        assertThatThrownBy(() -> service.deleteDocument(id,3L)).isInstanceOf(vn.edu.learningai.exception.ApiException.class);
        assertThat(docs(id)).isEqualTo(1);
        assertThat(root.resolve(key)).exists();
    }
    @Test void successfulLessonDeletionRemovesMetadataAndFiles() {
        long id=upload(); String key=key(id);
        service.delete(1L,2L);
        assertThat(docs(id)).isZero();
        assertThat(root.resolve(key)).doesNotExist();
        assertThat(jdbc.sql("SELECT COUNT(*) FROM lessons WHERE id=1").query(Long.class).single()).isZero();
    }
}
