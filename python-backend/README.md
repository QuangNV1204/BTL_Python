# Backend Python — FastAPI port của java-backend

Bản chuyển từ `java-backend` sang FastAPI, Pydantic và SQLAlchemy. Giữ nguyên:
route, contract JSON (snake_case, BIGINT dạng string, timestamp ISO-8601 UTC),
mã lỗi/HTTP status, schema MySQL (dùng chung `database/migrations`, không tạo schema
riêng), luồng transaction và quyền theo object.

## Chạy

```bash
cd python-backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8080        # hoặc: python -m app.main
```

http://localhost:8080/docs để xem OpenAPI; frontend trỏ `VITE_API_URL=http://localhost:8080/api/v1`.

### Cấu hình

`Settings` đọc theo thứ tự ưu tiên: **biến môi trường → `python-backend/.env` →
`java-backend/.env` → mặc định**. Vì vậy chạy được ngay với `.env` sẵn có của Java
(`DBMS_*`, `AI_*`, `MAIL_*`, `APP_*`); file `python-backend/.env` chỉ cần chứa giá trị
muốn ghi đè.

Điều kiện bắt buộc:

- `JWT_SIGNING_KEY` phải là **Base64 của >= 32 byte**, không phải chuỗi thường
  (Java giải mã bằng `Base64.getDecoder()`; chuỗi sai làm login lỗi 500). Sinh mới:
  `python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"`.
- Schema do Flyway của `java-backend` tạo; backend Python chỉ đọc/ghi, không `create_all`
  và không chạy migration riêng (xem `docs/05-delivery/python-migration.md`).
- SQLite không dùng cho production: chỉ dành cho test (`python -m pytest`).
- `.env` local của Python đang dùng key mới, nên user cũ cần đăng nhập lại — access/refresh
  token đã phát hành bằng key khác sẽ bị từ chối (401). Dữ liệu DB không bị ảnh hưởng.

### Chạy test

```bash
python -m pytest          # 54 test, SQLite tạm, không cần MySQL
```

## Bố cục

```text
app/
  main.py                 create_app: middleware, error handler, router
  shared/
    auth/                 JWT, refresh session/cookie, middleware Bearer, principal
    config/               Settings từ biến môi trường
    database/             Base, ORM model, session/transaction, hooks, locking
    domain/               Enum dùng trên wire
    error/                ErrorCode, ApiException, request id
    http/                 serialize wire, error handler, dependency
    mail/                 SMTP + template HTML (sao từ Java)
    pagination/           PageResponse
    storage/              thumbnail, tài liệu, trích text PDF/DOCX/TXT
    validation/           YouTube URL, parse BIGINT/positive int
  modules/<module>/
    api/                  router + schema Pydantic
    application/          service, use case, transaction
    domain/               rule thuần (module ai)
    infrastructure/       adapter AI (mock/llm), prompt
```

Luồng quyền giữ như Java: kiểm tra role ở router (tương đương `SecurityConfig`) và
kiểm tra quyền theo object ở service (owner khóa học, giảng viên của lesson…).

## Khác biệt kỹ thuật có chủ đích

| Hạng mục | Java | Python |
|---|---|---|
| Trích text tài liệu | Apache Tika | `pypdf` (PDF), `python-docx` (DOCX), đọc trực tiếp TXT |
| MapStruct/Lombok | DTO + mapper | Pydantic schema + hàm `*_response` |
| JPA/Hibernate | entity + repository | SQLAlchemy 2.0 ORM + `select()` |
| Migration | Flyway | Không chạy migration; dùng chung SQL của Java |
| Transaction request | `@Transactional` | Một `Session`/request; commit khi 2xx, rollback khi lỗi |
| Sự kiện sau commit | `TransactionSynchronization` | `app.shared.database.hooks` |
| JSON body quiz/attempt | Jackson `@JsonCreator` | Pydantic `*.from_json` cho dict thô |

Test: `tests/` có kiểm thử contract AI và các luồng HTTP chính (auth, course,
lesson, document, quiz, draft-save, flashcard, attempt, statistics).
