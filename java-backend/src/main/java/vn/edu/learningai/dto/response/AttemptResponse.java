package vn.edu.learningai.dto.response;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;
import vn.edu.learningai.common.enums.AttemptStatus;

import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AttemptResponse(String id, String quizId, String studentId, AttemptStatus status,
                              int totalQuestions, Instant startedAt) {
}
