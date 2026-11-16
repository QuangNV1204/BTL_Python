package vn.edu.learningai.dto.response;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;
import vn.edu.learningai.common.enums.AttemptStatus;

import java.math.BigDecimal;
import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AttemptSummaryResponse(
    String id, String quizId, String quizTitle, String courseId, String courseTitle,
    AttemptStatus status, BigDecimal score, Instant startedAt, Instant submittedAt
) {}
