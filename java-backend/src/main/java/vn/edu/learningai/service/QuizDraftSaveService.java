package vn.edu.learningai.service;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;
import vn.edu.learningai.common.enums.QuizStatus;
import vn.edu.learningai.common.enums.UserRole;
import vn.edu.learningai.dto.request.SaveQuizDraftRequest;
import vn.edu.learningai.dto.request.UpdateQuizRequest;
import vn.edu.learningai.dto.response.QuizAuthorResponse;
import vn.edu.learningai.exception.ApiException;
import vn.edu.learningai.exception.ErrorCode;
import vn.edu.learningai.repository.QuestionRepository;
import vn.edu.learningai.repository.QuizContextRepository;
import vn.edu.learningai.repository.QuizRepository;
import vn.edu.learningai.security.SecurityHelper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.HexFormat;

@Service
@RequiredArgsConstructor
public class QuizDraftSaveService {
    private final QuizRepository quizzes;
    private final QuestionRepository questions;
    private final QuizContextRepository context;
    private final SecurityHelper security;
    private final QuizService quizService;
    private final JdbcClient jdbc;
    private final JsonMapper json;

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public QuizAuthorResponse save(long quizId, SaveQuizDraftRequest request) {
        var actor = security.getCurrentUser();
        var quiz = quizzes.findByIdForUpdate(quizId).orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND));
        var lesson = context.findLesson(quiz.getLessonId()).orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND));
        if (actor.getRole() != UserRole.ADMIN && (actor.getRole() != UserRole.TEACHER
                || !actor.getId().equals(lesson.teacherId()))) throw new ApiException(ErrorCode.FORBIDDEN);
        String hash = hash(json.writeValueAsString(request));
        var receipt = jdbc.sql("""
            SELECT payload_hash,response_json FROM quiz_draft_save_receipts
            WHERE quiz_id=:quiz AND actor_id=:actor AND request_id=:request
            """).param("quiz",quizId).param("actor",actor.getId()).param("request",request.requestId())
            .query((rs,n) -> new Receipt(rs.getString(1),rs.getString(2))).optional();
        if (receipt.isPresent()) {
            if (!hash.equals(receipt.get().hash())) throw new ApiException(ErrorCode.INVALID_STATE,
                "request_id was already used with a different payload");
            return json.readValue(receipt.get().response(),QuizAuthorResponse.class);
        }
        if (quiz.getStatus() != QuizStatus.DRAFT) throw new ApiException(ErrorCode.INVALID_STATE,"Only DRAFT quizzes can be changed");
        if (context.hasLearningHistory(quizId)) throw new ApiException(ErrorCode.RESOURCE_IN_USE,"Quiz has learning history");
        var current = questions.findByQuizIdOrderByOrderIndexAsc(quizId);
        var ids = current.stream().map(q -> q.getId()).collect(java.util.stream.Collectors.toSet());
        var wanted = new HashSet<Long>();
        for (var item : request.questions()) {
            item.question().validate();
            if (item.id()!=null && (!ids.contains(item.id()) || !wanted.add(item.id()))) {
                throw new ApiException(ErrorCode.VALIDATION_ERROR,"Question id must belong to this quiz and occur once");
            }
        }
        // Reuse established ownership/history/provenance validation within this one transaction.
        for (var question : current) if (!wanted.contains(question.getId())) quizService.deleteQuestion(question.getId());
        long base = Math.max(current.stream().mapToLong(q -> q.getOrderIndex()).max().orElse(-1),request.questions().size())+1;
        if (base+current.size()>Integer.MAX_VALUE) throw new ApiException(ErrorCode.INVALID_STATE,"Question order limit exceeded");
        int position=0;
        for (var question : current) if (wanted.contains(question.getId())) question.setOrderIndex((int)base+position++);
        questions.flush();
        quizService.update(quizId,new UpdateQuizRequest(request.title(),null));
        for (var item : request.questions()) {
            if (item.id()==null) quizService.addQuestion(quizId,item.question());
            else quizService.replaceQuestion(item.id(),item.question());
        }
        var result = (QuizAuthorResponse) quizService.get(quizId);
        jdbc.sql("""
            INSERT INTO quiz_draft_save_receipts(quiz_id,actor_id,request_id,payload_hash,response_json)
            VALUES(:quiz,:actor,:request,:hash,:response)
            """).param("quiz",quizId).param("actor",actor.getId()).param("request",request.requestId())
            .param("hash",hash).param("response",json.writeValueAsString(result)).update();
        return result;
    }

    private String hash(String payload) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(payload.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    private record Receipt(String hash,String response) {}
}
