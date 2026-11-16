package vn.edu.learningai.service;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Base64;
import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named = "QUIZ_TEST_MYSQL_URL",
    matches = "jdbc:mysql://[^/]+/learningai_quiz_test_history(?:\\?.*)?")
@Sql("/test-fixtures.sql")
class AttemptHistoryMySqlIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry properties) {
        properties.add("spring.datasource.url", () -> System.getenv("QUIZ_TEST_MYSQL_URL"));
        properties.add("spring.datasource.username", () -> System.getenv("QUIZ_TEST_MYSQL_USERNAME"));
        properties.add("spring.datasource.password", () -> System.getenv("QUIZ_TEST_MYSQL_PASSWORD"));
        properties.add("spring.jpa.show-sql", () -> false);
        properties.add("jwt.jwt-signing-key", () -> Base64.getEncoder().encodeToString(new byte[32]));
    }

    @BeforeEach
    void seed() {
        jdbc.sql("""
            INSERT INTO quizzes(id,lesson_id,title,status,created_by) VALUES
            (30,1,'Quiz A','PUBLISHED',2),(31,3,'Quiz B','PUBLISHED',3);
            """).update();
        jdbc.sql("""
            INSERT INTO quiz_attempts(id,quiz_id,student_id,status,total_questions,score,correct_count,started_at,submitted_at)
            VALUES (50,30,4,'SUBMITTED',3,66.67,2,'2026-11-14 00:00:00','2026-11-14 00:05:00'),
                   (51,30,4,'IN_PROGRESS',3,NULL,NULL,'2026-11-14 00:00:00',NULL),
                   (52,30,6,'SUBMITTED',3,100,3,'2026-11-14 00:00:00','2026-11-14 00:05:00'),
                   (53,31,4,'SUBMITTED',3,0,0,'2026-11-13 00:00:00','2026-11-13 00:05:00');
            """).update();
    }

    private String token(String email) throws Exception {
        var response = mvc.perform(post("/api/v1/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"" + email + "\",\"password\":\"DemoPass123!\"}"))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return JsonPath.read(response, "$.access_token");
    }

    @Test
    void accountsHaveIsolatedPagesAndCounts() throws Exception {
        String a = token("student.a@test.local");
        mvc.perform(get("/api/v1/users/me/attempts?page_size=1").header("Authorization", "Bearer " + a))
            .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(3))
            .andExpect(jsonPath("$.items.length()").value(1))
            .andExpect(jsonPath("$.items[0].id").value("51"))
            .andExpect(jsonPath("$.items[0].score").value(org.hamcrest.Matchers.nullValue()))
            .andExpect(jsonPath("$.items[0].submitted_at").value(org.hamcrest.Matchers.nullValue()))
            .andExpect(jsonPath("$.items[0].started_at").value("2026-11-14T00:00:00Z"))
            .andExpect(jsonPath("$.items[0].review").doesNotExist());
        mvc.perform(get("/api/v1/users/me/attempts?page=2&page_size=1").header("Authorization", "Bearer " + a))
            .andExpect(status().isOk()).andExpect(jsonPath("$.items[0].id").value("50"))
            .andExpect(jsonPath("$.items[0].score").value(66.67));
        mvc.perform(get("/api/v1/users/me/attempts").header("Authorization", "Bearer " + token("student.b@test.local")))
            .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(1))
            .andExpect(jsonPath("$.items[0].id").value("52"));
    }

    @Test
    void filtersApplyToBothItemsAndTotalAndHistorySurvivesArchive() throws Exception {
        String a = token("student.a@test.local");
        jdbc.sql("UPDATE courses SET archived_at=UTC_TIMESTAMP(),is_published=FALSE WHERE id=2").update();
        jdbc.sql("DELETE FROM course_members WHERE student_id=4 AND course_id=2").update();
        for (String filter : List.of("quiz_id=30", "course_id=2", "quiz_id=30&course_id=2")) {
            mvc.perform(get("/api/v1/users/me/attempts?" + filter).header("Authorization", "Bearer " + a))
                .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(2))
                .andExpect(jsonPath("$.items.length()").value(2))
                .andExpect(jsonPath("$.items[0].course_id").value("2"));
        }
        for (String query : List.of("quiz_id=30&course_id=4", "quiz_id=999", "page=99")) {
            mvc.perform(get("/api/v1/users/me/attempts?" + query).header("Authorization", "Bearer " + a))
                .andExpect(status().isOk()).andExpect(jsonPath("$.items").isEmpty())
                .andExpect(jsonPath("$.total").value(query.equals("page=99") ? 3 : 0));
        }
    }

    @Test
    void guestWrongRolesAndInactiveAccountAreDenied() throws Exception {
        mvc.perform(get("/api/v1/users/me/attempts")).andExpect(status().isUnauthorized());
        for (String email : List.of("teacher.a@test.local", "admin@test.local")) {
            mvc.perform(get("/api/v1/users/me/attempts").header("Authorization", "Bearer " + token(email)))
                .andExpect(status().isForbidden());
        }
        String a = token("student.a@test.local");
        jdbc.sql("UPDATE users SET is_active=FALSE WHERE id=4").update();
        mvc.perform(get("/api/v1/users/me/attempts").header("Authorization", "Bearer " + a))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidPaginationIsRejectedThroughRealSecurityChain() throws Exception {
        String a = token("student.a@test.local");
        for (String query : List.of("page=0", "page_size=0", "page_size=101", "page=2147483648")) {
            mvc.perform(get("/api/v1/users/me/attempts?" + query).header("Authorization", "Bearer " + a))
                .andExpect(status().isBadRequest());
        }
    }

    @Test
    void emptyHistoryAndForgedStudentIdCannotExposeAnotherStudent() throws Exception {
        String b = token("student.b@test.local");
        jdbc.sql("DELETE FROM quiz_attempts WHERE student_id=6").update();
        mvc.perform(get("/api/v1/users/me/attempts?student_id=4").header("Authorization", "Bearer " + b))
            .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(0))
            .andExpect(jsonPath("$.items").isEmpty());
    }
}
