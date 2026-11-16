# Migration, seed và truy vấn

Một nguồn SQL MySQL trong `database/migrations/`, đặt tên theo Flyway: `V1__initial_schema.sql`, `V2__...sql`. Java build copy thư mục này vào classpath `db/migration` (xem `java-backend/pom.xml`). Python dùng **cùng file và bảng lịch sử migration** (`flyway_schema_history`), không chạy runner thứ hai. Nếu runner khác, phải xác minh lịch sử tương thích, không để hai runner apply lại.

Không dùng JPA ddl-auto=create/update ở môi trường nhóm; ORM validate schema. Không để SQLAlchemy create_all hoặc Alembic tạo schema song song. Áp migration một lần trước app startup; version/checksum có tracking; migration đã áp không sửa lại.

Thay đổi: ghi ADR nếu phá tương thích → cập nhật từ điển/ERD/contract → SQL migration → dữ liệu/ORM hai phía → kiểm tra DB mới và DB đã có dữ liệu. Với SQLite/H2 không thể chứng minh ENUM/CHECK/unique có điều kiện/transaction giống MySQL; kiểm tra trên MySQL thật cho các invariant liên quan.

**Nâng cấp V8 upload staging:** dừng/drain uploaders phiên bản cũ trước migrate và chỉ khởi động worker/uploaders mới sau đó; không rolling-mix protocol cũ/mới. V8 gắn job cũ thành DELETE, không thể bảo vệ một uploader cũ đang ngủ rồi ghi file muộn. STAGING tombstones giữ bền vững, không tự hết hạn; theo dõi dung lượng bảng và chỉ bảo trì khi đã chứng minh không còn writer liên quan. Bảo đảm ở đây là process/transaction-crash recovery, không phải mất điện/hỏng ổ đĩa (cần storage durability/backup riêng).

Database local từng áp bản chưa chia sẻ `V6__document_cleanup_jobs` không được tự sửa checksum hoặc history để giả thành schema hiện hành. Dùng database disposable mới và copy dữ liệu test cần giữ bằng column whitelist/transaction; database nhóm/production phải có kế hoạch migration riêng được duyệt.

Seed tách dev/demo/test. Fixtures có admin, 2 teacher, 2 student, teacher request, khóa free Published, khóa Draft, khóa archived, quiz Draft/Published/Closed, flashcard Draft/Published, attempt Submitted và bỏ trống. Password demo lấy từ cấu hình/test fixture, hash hợp lệ; không tái sử dụng mật khẩu thật. Không reset DB có dữ liệu nhóm khi chưa xác định đó là DB test.

Truy vấn cần chuẩn bị: marketplace số enrolled; average score/quiz; số lượt Submitted; câu sai nhiều (có bỏ trống); best score/student; completion rate với mẫu số xác định; thống kê admin. Mỗi query ghi mục đích, quyền, parameter, bảng, expected result và EXPLAIN nếu nói về tối ưu. Hoàn thành với 0 enrollment/0 quiz phải có fixture.
