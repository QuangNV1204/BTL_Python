package vn.edu.learningai.controller;

import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import vn.edu.learningai.dto.request.SubmitAttemptRequest;
import vn.edu.learningai.dto.response.AttemptResponse;
import vn.edu.learningai.dto.response.AttemptResultResponse;
import vn.edu.learningai.exception.ApiException;
import vn.edu.learningai.exception.ErrorCode;
import vn.edu.learningai.service.AttemptService;

import java.net.URI;

@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class AttemptController {
    private final AttemptService attemptService;

    @PostMapping("/quizzes/{quiz_id}/attempts")
    public ResponseEntity<AttemptResponse> start(@PathVariable("quiz_id") String quizId) {
        var result = attemptService.start(positiveLong(quizId, "quiz_id"));
        var builder = ResponseEntity.status(result.created() ? HttpStatus.CREATED : HttpStatus.OK);
        if (result.created()) {
            builder.location(URI.create("/api/v1/attempts/" + result.attempt().id()));
        }
        return builder.body(result.attempt());
    }

    @PostMapping("/attempts/{attempt_id}/submit")
    public AttemptResultResponse submit(@PathVariable("attempt_id") String attemptId,
                                        @RequestBody SubmitAttemptRequest request) {
        return attemptService.submit(positiveLong(attemptId, "attempt_id"), request);
    }

    @GetMapping("/attempts/{attempt_id}")
    public Object get(@PathVariable("attempt_id") String attemptId) {
        return attemptService.get(positiveLong(attemptId, "attempt_id"));
    }

    private static long positiveLong(String value, String field) {
        if (!value.matches("[1-9][0-9]{0,18}")) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, field + " must be a positive BIGINT");
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException exception) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, field + " exceeds the signed BIGINT range");
        }
    }
}
