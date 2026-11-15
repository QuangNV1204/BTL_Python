package vn.edu.learningai.dto.response;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;
import vn.edu.learningai.common.enums.AttemptStatus;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AttemptResultResponse(String id, String quizId, String quizTitle, String studentId,
                                    AttemptStatus status, BigDecimal score, int totalQuestions,
                                    int correctCount, Instant startedAt, Instant submittedAt,
                                    List<Review> review) {
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Review(String questionId, String questionContent, String selectedOptionId,
                         boolean isCorrect, String correctOptionId, String explanation,
                         List<Option> options) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Option(String id, String content) {}
}
