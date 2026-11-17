# Statistics prototype UI checks

## Scope

Dashboard changes to course, quiz and system statistics follow
`docs/03-experience/prototype.html` and existing light/dark tokens. The initial
UI commits did not change the backend. A subsequent Python API extension adds
`active_teachers` and `active_students` without changing existing count semantics
or database schema. No production data changes.

- Course: four KPI tiles, completion circle and counts, course selector,
  published quiz table, partial error states and quiz detail navigation.
- Quiz: three KPI tiles, top-five wrong-question bars and underlying data table,
  best-score table. Student IDs are labeled as IDs; no invented student names.
- System: five KPI tiles and definitions matching current backend queries.
  Role proportions now use explicit active-only Teacher and Student counts,
  excluding Admin. Existing `active_users` and `teachers` totals are preserved.
  When an older backend omits the new fields, UI shows a deployment notice;
  zero active Teacher/Student accounts produce an empty state rather than NaN.
- Existing paginated endpoints are traversed instead of truncating at 100 items.
  Null average scores remain unavailable, not zero.

## Verification

- `npm ci`: completed without changing package manifests/lockfile.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm test -- --test-concurrency=1`: 31 passed, zero failed/skipped.
- `npm run build`: passed, with the existing large-chunk warning.
- Static independent review: no confirmed findings in the scoped changes.

Browser checks used headless Edge against the actual production frontend served
by Vite preview. API calls were intercepted with **explicit QA fixtures**. This
verifies rendering/client behavior, not real authentication, database queries,
endpoint performance or MySQL integration.

- 12 page/theme/viewport combinations: course, quiz and system pages;
  light/dark; 1440px and 375px. No horizontal document overflow or uncaught
  page errors; all expected fixture endpoints were handled.
- Additional checks passed: zero-enrollment/zero-quiz course, partial quiz
  aggregate failure with course data preserved, and forbidden course statistics.
- Screenshots were inspected for desktop course/quiz, mobile course and system
  presentation. Wide tables scroll inside their container.
- External Google Fonts requests were blocked deliberately; fallback fonts were
  exercised. Error-case HTTP 500/403 were intentionally simulated.
- Dev-server smoke initially hit Vite `Outdated Optimize Dep` after test
  optimizers touched the cache; production preview was used for final UI checks.
- Parallel test execution hit a Windows resource limit during concurrent Vite
  optimization. The serial-concurrency invocation passed. No hooks were bypassed.

Chart accent checks passed the palette validator for light `#4F46E5` and dark
`#7C83EE` against the dark surface `#111827`. Labels/counts and a table view avoid
relying on color alone. The completion circle intentionally follows the existing
prototype.

## Live backend verification (separate from the fixture UI run)

A subsequent run connected the actual React frontend through Vite's `/api`
proxy to the unmodified group FastAPI backend and a dedicated MySQL 8.0.46
instance bound to loopback. Official Flyway Community 11.20.0 applied and
validated canonical V1–V9. No existing MySQL service/database was used.

The database contained synthetic QA users and records, not production data.
Accounts were provisioned directly with BCrypt hashes and verified timestamps.
Course publication state was set as a database fixture to isolate statistics;
this run does not claim coverage of the publication UI. Courses, lessons,
quizzes, questions, enrollment and attempts were otherwise exercised through
real HTTP endpoints. Mail/live AI were not exercised.

- Two actual submissions scored 100 and 50; a third attempt remained IN_PROGRESS.
- Course API: one enrollment, one published quiz, two submissions, one completed
  student, completion rate 100 percent.
- Quiz API: two submissions, one unique student, average 75, best score 100,
  one wrong answer on the second question. IN_PROGRESS was excluded.
- Aggregate API values were compared against direct SQL counts/AVG on the same
  disposable database, including system active users and teacher counts.
- Student and nonowner Teacher received 403 for course statistics; Teacher
  received 403 for system statistics.
- Browser logged in using the real login form as Teacher and Admin, opened
  course/quiz/system dashboards, and reloaded successfully with real refresh.
  Observed statistics responses were HTTP 200 and there were no uncaught page
  errors or horizontal document overflow at 1440px. Screenshots were inspected.
- This browser run used no `page.route`, `route.fulfill`, fake responses,
  dependency overrides or injected authentication tokens. Credentials and JWT
  signing keys remained local and untracked.

The live run confirms local frontend/backend/database connectivity for these
statistics paths. The deployed team environment, larger datasets, live error
states, concurrent mutations and full-system E2E remain outside this evidence.

## Active role API fix

Python now counts active users, all teachers, active teachers and active students
in one SQL statement. The first two fields keep their previous meanings. Role
percentages use `active_teachers + active_students`, excluding Admin and inactive
accounts; no new database table or migration is needed. Contract/payload docs
include the two fields. Java is not updated by this Python-scoped change.

- Backend suite: 59 passed (54 previous plus five active-role/authorization cases),
  using isolated SQLite. Cases include mixed active/inactive accounts, only one
  role, no active Teacher/Student, and Admin-only access.
- Frontend: 31 tests passed, including missing/zero/negative/invalid role fields,
  percentages 0/100 and a mixed role ratio. Typecheck/lint/build passed.
- OpenAPI validation passed.
- Live MySQL SQL comparison: active_users=4, teachers=2, active_teachers=2,
  active_students=1. API returned exactly those values.
- Browser used actual form login/network/backend on light/dark at 1440px/375px.
  All four cases showed Teacher 66.67 percent and Student 33.33 percent, no
  horizontal overflow or uncaught page errors. No response mocking was used.

The original 54-test report remains tied to baseline 513d20a. Do not retroactively
replace that report's test count without updating its tested version.

## PR review regressions

The review follow-up fixes four P2 issues and cancellation scheduling (P3):

- Only the current ten quiz rows request aggregates, with at most four active
  requests. IDs stay paired with results, including independent failures.
- Both PUBLISHED and CLOSED quizzes retain statistics navigation and status
  labels; the completion metric still counts currently PUBLISHED quizzes only.
- Active role additions are optional in the shared OpenAPI during compatibility.
  Old Java responses and extended Python responses both validate; Python still
  supplies the values. Missing values are not treated as zero.
- Pagination checks stable totals/page sizes, progress, exact page counts and
  duplicate IDs. Concurrent changes produce a retryable visible error instead
  of a silently incomplete list. Offset pagination cannot detect every same-count
  reorder without a server cursor/snapshot; this is not claimed as solved.
- Query cancellation reaches fetch, pagination and bounded workers. Abandoned
  queries stop scheduling new lessons/pages; AbortError is not a partial failure.

Follow-up verification:

- Backend: 60 passed on isolated SQLite, including shared compatibility regression.
- Frontend: 32 passed; typecheck/lint/build passed (existing large-chunk warning).
- OpenAPI validated; original Java-shaped and extended Python-shaped system
  response fixtures both passed schema validation.
- Browser fixture with 200 quizzes: only 10 aggregate calls on first page, 20
  total after page two, CLOSED detail link present; desktop1440/mobile375 both
  had no horizontal overflow or uncaught page errors. This is request-count UI
  verification, not a production load test.
- Repeated real browser login/reload/course/quiz/system smoke against local Python
  and disposable MySQL passed with statistics HTTP200 and no page errors.
- Independent static re-review confirmed all five reviewed findings addressed;
  no additional actionable correctness issue was found in that bounded scope.

No production database mutation, merge or deploy was performed. Deployment smoke
and infrastructure checks remain the group's responsibility after review/merge.
