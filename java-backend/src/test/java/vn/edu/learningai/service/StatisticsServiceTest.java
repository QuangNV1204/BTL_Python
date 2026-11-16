package vn.edu.learningai.service;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import vn.edu.learningai.security.SecurityHelper;
import vn.edu.learningai.entity.User;
import vn.edu.learningai.common.enums.UserRole;
import vn.edu.learningai.exception.ApiException;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

class StatisticsServiceTest {
    @Test void nonAdminCannotQuerySystemAggregates() {
        var jdbc=mock(JdbcClient.class);
        var security=mock(SecurityHelper.class,withSettings().mockMaker(org.mockito.MockMakers.SUBCLASS));
        when(security.getCurrentUser()).thenReturn(User.builder().id(4L).role(UserRole.STUDENT).build());
        assertThatThrownBy(()->new StatisticsService(jdbc,security).system()).isInstanceOf(ApiException.class);
        verifyNoInteractions(jdbc);
    }
}
