package vn.edu.learningai.service;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Base64;

import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named = "QUIZ_TEST_MYSQL_URL",
    matches = "jdbc:mysql://[^/]+/learningai_quiz_test(?:_[A-Za-z0-9]+)?(?:\\?.*)?")
@Sql("/test-fixtures.sql")
class LessonTranscriptMySqlIntegrationTest {
    @Autowired MockMvc mvc;

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry properties) {
        properties.add("spring.datasource.url", () -> System.getenv("QUIZ_TEST_MYSQL_URL"));
        properties.add("spring.datasource.username", () -> System.getenv("QUIZ_TEST_MYSQL_USERNAME"));
        properties.add("spring.datasource.password", () -> System.getenv().getOrDefault("QUIZ_TEST_MYSQL_PASSWORD", ""));
        properties.add("spring.jpa.show-sql", () -> false);
        properties.add("jwt.jwt-signing-key", () -> Base64.getEncoder().encodeToString(new byte[32]));
    }

    private String login(String email) throws Exception {
        String response = mvc.perform(post("/api/v1/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"" + email + "\",\"password\":\"DemoPass123!\"}"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();
        return JsonPath.read(response, "$.access_token");
    }

    @Test
    void enrolledStudentDoesNotReceivePrivateTranscriptInDetailOrList() throws Exception {
        String studentToken = login("student.a@test.local");

        mvc.perform(get("/api/v1/lessons/1").header("Authorization", "Bearer " + studentToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("1"))
            .andExpect(jsonPath("$.transcript_text").value(nullValue()));

        mvc.perform(get("/api/v1/courses/2/lessons").header("Authorization", "Bearer " + studentToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value("1"))
            .andExpect(jsonPath("$[0].transcript_text").value(nullValue()))
            .andExpect(jsonPath("$[1].id").value("2"))
            .andExpect(jsonPath("$[1].transcript_text").value(nullValue()));
    }

    @Test
    void ownerAndAdminReceivePrivateTranscriptInDetailAndList() throws Exception {
        for (String email : new String[]{"teacher.a@test.local", "admin@test.local"}) {
            String token = login(email);

            mvc.perform(get("/api/v1/lessons/1").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.transcript_text").value("transcript bi mat 1"));

            mvc.perform(get("/api/v1/courses/2/lessons").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].transcript_text").value("transcript bi mat 1"))
                .andExpect(jsonPath("$[1].transcript_text").value("transcript bi mat 2"));
        }
    }

    @Test
    void unauthorizedUsersCannotReadLessons() throws Exception {
        String unauthenticatedDetail = "/api/v1/lessons/1";
        mvc.perform(get(unauthenticatedDetail)).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/courses/2/lessons")).andExpect(status().isUnauthorized());

        String unenrolledStudent = login("student.b@test.local");
        mvc.perform(get(unauthenticatedDetail).header("Authorization", "Bearer " + unenrolledStudent))
            .andExpect(status().isForbidden());
        mvc.perform(get("/api/v1/courses/2/lessons").header("Authorization", "Bearer " + unenrolledStudent))
            .andExpect(status().isForbidden());

        String otherTeacher = login("teacher.b@test.local");
        mvc.perform(get(unauthenticatedDetail).header("Authorization", "Bearer " + otherTeacher))
            .andExpect(status().isForbidden());
        mvc.perform(get("/api/v1/courses/2/lessons").header("Authorization", "Bearer " + otherTeacher))
            .andExpect(status().isForbidden());
    }
}
