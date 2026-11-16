package vn.edu.learningai.dto.request;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;

class SaveQuizDraftRequestTest {
    private final JsonMapper json=JsonMapper.builder().build();
    private String body(String questions) {
        return "{\"request_id\":\"11111111-1111-4111-8111-111111111111\",\"title\":\"Quiz\",\"questions\":"+questions+"}";
    }
    @Test void acceptsEmptyDraftAndRequiredNullableExplanation() {
        assertThat(json.readValue(body("[]"),SaveQuizDraftRequest.class).questions()).isEmpty();
        String q="{\"id\":\"1\",\"content\":\"Q\",\"explanation\":null,\"order_index\":0,\"options\":[{\"content\":\"A\",\"is_correct\":true,\"order_index\":0},{\"content\":\"B\",\"is_correct\":false,\"order_index\":1}]}";
        assertThat(json.readValue(body("["+q+"]"),SaveQuizDraftRequest.class).questions().get(0).id()).isEqualTo(1L);
    }
    @ParameterizedTest
    @ValueSource(strings={"{}","[]","{\"request_id\":\"bad\",\"title\":\"Q\",\"questions\":[]}",
        "{\"request_id\":\"11111111-1111-4111-8111-111111111111\",\"title\":\"Q\",\"questions\":[],\"score\":100}"})
    void rejectsMalformedAndServerOwnedFields(String input) {
        assertThatThrownBy(()->json.readValue(input,SaveQuizDraftRequest.class)).isInstanceOf(RuntimeException.class);
    }
}
