package vn.edu.learningai.controller;

import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import vn.edu.learningai.dto.request.SaveQuizDraftRequest;
import vn.edu.learningai.dto.response.QuizAuthorResponse;
import vn.edu.learningai.exception.ApiException;
import vn.edu.learningai.exception.ErrorCode;
import vn.edu.learningai.service.QuizDraftSaveService;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/quizzes")
public class QuizDraftSaveController {
    private final QuizDraftSaveService service;

    @PutMapping("/{quiz_id}/draft")
    public QuizAuthorResponse save(@PathVariable("quiz_id") String value, @RequestBody SaveQuizDraftRequest request) {
        try {
            if (!value.matches("[1-9][0-9]{0,18}")) throw new NumberFormatException();
            return service.save(Long.parseLong(value),request);
        } catch (NumberFormatException e) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"quiz_id must be a positive signed BIGINT");
        }
    }
}
