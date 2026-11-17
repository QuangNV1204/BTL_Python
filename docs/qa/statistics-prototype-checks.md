# Statistics prototype UI checks

## Scope

Frontend-only change to course, quiz and system statistics, based on
`docs/03-experience/prototype.html` and existing light/dark tokens. No API,
backend, schema or production data changes.

- Course: four KPI tiles, completion circle and counts, course selector,
  published quiz table, partial error states and quiz detail navigation.
- Quiz: three KPI tiles, top-five wrong-question bars and underlying data table,
  best-score table. Student IDs are labeled as IDs; no invented student names.
- System: five KPI tiles and definitions matching current backend queries.
  Role proportions are explicitly unavailable: `active_users` includes Admin,
  whereas `teachers` includes inactive accounts. Subtracting these values would
  not produce a valid active-student count.
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
System role proportions still require a compatible authorized data breakdown;
the unavailable-data notice is not an API connectivity error.
