package vn.edu.learningai.repository;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import vn.edu.learningai.common.enums.AttemptStatus;
import vn.edu.learningai.dto.response.AttemptSummaryResponse;
import vn.edu.learningai.dto.response.PageResponse;

@Repository
@RequiredArgsConstructor
public class AttemptHistoryRepository {
    private final JdbcClient jdbc;

    public PageResponse<AttemptSummaryResponse> findMine(Long studentId, Long quizId, Long courseId,
                                                        int page, int pageSize) {
        String from = """
            FROM quiz_attempts a
            JOIN quizzes q ON q.id = a.quiz_id
            JOIN lessons l ON l.id = q.lesson_id
            JOIN courses c ON c.id = l.course_id
            WHERE a.student_id = :student_id
            """;
        if (quizId != null) from += " AND q.id = :quiz_id";
        if (courseId != null) from += " AND c.id = :course_id";

        var count = bind(jdbc.sql("SELECT COUNT(*) " + from), studentId, quizId, courseId);
        long total = count.query(Long.class).single();
        var query = bind(jdbc.sql("""
            SELECT a.id, a.quiz_id, q.title AS quiz_title, c.id AS course_id,
                   c.title AS course_title, a.status, a.score, a.started_at, a.submitted_at
            """ + from + " ORDER BY a.started_at DESC, a.id DESC LIMIT :limit OFFSET :offset"),
            studentId, quizId, courseId)
            .param("limit", pageSize).param("offset", ((long) page - 1) * pageSize);
        var items = query.query((rs, row) -> {
            var submitted = rs.getTimestamp("submitted_at");
            return new AttemptSummaryResponse(
                Long.toString(rs.getLong("id")), Long.toString(rs.getLong("quiz_id")),
                rs.getString("quiz_title"), Long.toString(rs.getLong("course_id")),
                rs.getString("course_title"), AttemptStatus.valueOf(rs.getString("status")),
                rs.getBigDecimal("score"), rs.getTimestamp("started_at").toInstant(),
                submitted == null ? null : submitted.toInstant());
        }).list();
        return new PageResponse<>(items, page, pageSize, total);
    }

    private JdbcClient.StatementSpec bind(JdbcClient.StatementSpec query, Long studentId,
                                           Long quizId, Long courseId) {
        query.param("student_id", studentId);
        if (quizId != null) query.param("quiz_id", quizId);
        if (courseId != null) query.param("course_id", courseId);
        return query;
    }
}
