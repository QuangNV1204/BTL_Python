package vn.edu.learningai.controller;

import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import vn.edu.learningai.service.StatisticsService;
import vn.edu.learningai.exception.ApiException;
import vn.edu.learningai.exception.ErrorCode;

@RestController
@RequestMapping("/api/v1/statistics")
@RequiredArgsConstructor
public class StatisticsController {
    private final StatisticsService service;

    @GetMapping("/courses/{id}")
    public StatisticsService.CourseStatistics course(@PathVariable String id) { return service.course(id(id)); }
    @GetMapping("/quizzes/{id}")
    public StatisticsService.QuizStatistics quiz(@PathVariable String id) { return service.quiz(id(id)); }
    @GetMapping("/system")
    public StatisticsService.SystemStatistics system() { return service.system(); }

    private long id(String value) {
        try {
            if (!value.matches("[1-9][0-9]{0,18}")) throw new NumberFormatException();
            return Long.parseLong(value);
        } catch (NumberFormatException e) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"id must be a positive signed BIGINT");
        }
    }
}
