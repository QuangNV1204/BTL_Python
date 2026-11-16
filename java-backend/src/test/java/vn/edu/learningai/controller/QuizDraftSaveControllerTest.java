package vn.edu.learningai.controller;

import org.junit.jupiter.api.Test;
import org.mockito.MockMakers;
import org.springframework.http.MediaType;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.json.JsonMapper;
import vn.edu.learningai.dto.response.QuizAuthorResponse;
import vn.edu.learningai.common.enums.QuizStatus;
import vn.edu.learningai.service.QuizDraftSaveService;
import vn.edu.learningai.exception.GlobalExceptionHandler;
import java.time.Instant;
import java.util.List;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class QuizDraftSaveControllerTest {
    @Test void acceptsAtomicPutAndRejectsUnknownFields() throws Exception {
        var service=mock(QuizDraftSaveService.class,withSettings().mockMaker(MockMakers.SUBCLASS));
        var json=JsonMapper.builder().build();
        var mvc=MockMvcBuilders.standaloneSetup(new QuizDraftSaveController(service))
            .setControllerAdvice(new GlobalExceptionHandler(json))
            .setMessageConverters(new JacksonJsonHttpMessageConverter(json)).build();
        when(service.save(eq(30L),any())).thenReturn(new QuizAuthorResponse("30","10","Q",QuizStatus.DRAFT,Instant.now(),List.of()));
        String body="{\"request_id\":\"11111111-1111-4111-8111-111111111111\",\"title\":\"Q\",\"questions\":[]}";
        mvc.perform(put("/api/v1/quizzes/30/draft").contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk()).andExpect(jsonPath("$.id").value("30"));
        clearInvocations(service);
        mvc.perform(put("/api/v1/quizzes/30/draft").contentType(MediaType.APPLICATION_JSON).content(body.replace("\"title\"","\"score\"")))
            .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }
}
