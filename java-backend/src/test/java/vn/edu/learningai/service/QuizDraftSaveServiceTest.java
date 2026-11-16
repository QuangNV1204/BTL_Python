package vn.edu.learningai.service;

import org.junit.jupiter.api.Test;
import org.mockito.MockMakers;
import org.springframework.jdbc.core.simple.JdbcClient;
import tools.jackson.databind.json.JsonMapper;
import vn.edu.learningai.common.enums.UserRole;
import vn.edu.learningai.entity.Quiz;
import vn.edu.learningai.entity.User;
import vn.edu.learningai.dto.request.SaveQuizDraftRequest;
import vn.edu.learningai.repository.*;
import vn.edu.learningai.security.SecurityHelper;
import vn.edu.learningai.exception.ApiException;
import java.util.List;
import java.util.Optional;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

class QuizDraftSaveServiceTest {
    @Test void unrelatedTeacherCannotReadSaveReceiptsOrMutate() {
        var quizzes=mock(QuizRepository.class);
        var questions=mock(QuestionRepository.class);
        var context=mock(QuizContextRepository.class,withSettings().mockMaker(MockMakers.SUBCLASS));
        var security=mock(SecurityHelper.class,withSettings().mockMaker(MockMakers.SUBCLASS));
        var service=mock(QuizService.class,withSettings().mockMaker(MockMakers.SUBCLASS));
        var jdbc=mock(JdbcClient.class);
        when(security.getCurrentUser()).thenReturn(User.builder().id(3L).role(UserRole.TEACHER).build());
        when(quizzes.findByIdForUpdate(30L)).thenReturn(Optional.of(Quiz.builder().id(30L).lessonId(10L).build()));
        when(context.findLesson(10L)).thenReturn(Optional.of(new QuizContextRepository.LessonContext(20L,2L)));
        var save=new QuizDraftSaveService(quizzes,questions,context,security,service,jdbc,JsonMapper.builder().build());
        assertThatThrownBy(()->save.save(30L,new SaveQuizDraftRequest("key","Q",List.of()))).isInstanceOf(ApiException.class);
        verifyNoInteractions(jdbc,service,questions);
    }
}
