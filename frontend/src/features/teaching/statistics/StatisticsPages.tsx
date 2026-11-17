import type { CSSProperties, ReactNode } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Alert, Card, Progress, Select, Table, Tag, theme, Tooltip } from 'antd'
import { Link, useParams, useSearchParams } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '../../../shared/components/PageState'
import { usePageHeader } from '../../../shared/components/pageHeader'
import { paths } from '../../../shared/routing/paths'
import { formatDateTime } from '../../../shared/utils/format'
import { getQuiz, quizKeys } from '../quizzes/quiz.api'
import {
  formatScore, getAllOwnedCourses, getCourseStats, getPublishedCourseQuizzes, getQuizStats, getSystemStats,
} from './statistics.api'
import './statistics.css'

const number = (value: number) => value.toLocaleString('vi-VN')

function StatisticsLayout({ children }: { children: ReactNode }) {
  const { token } = theme.useToken()
  return <div className="statistics-page" style={{ '--statistics-accent': token.colorPrimary } as CSSProperties}>{children}</div>
}

function StatsSummary({ items }: { items: { label: string; value: ReactNode; detail?: string }[] }) {
  return <div className={`statistics-summary statistics-summary-${items.length}`}>
    {items.map(item => <Card key={item.label} className="statistics-kpi">
      <span className="statistics-muted">{item.label}</span>
      <strong className="statistics-value">{item.value}</strong>
      {item.detail && <small className="statistics-muted">{item.detail}</small>}
    </Card>)}
  </div>
}

function UpdatedAt({ value }: { value?: string }) {
  return <span className="statistics-muted">{value ? `Cập nhật lúc ${formatDateTime(value)} (giờ Việt Nam)` : 'Đang tải thời điểm cập nhật…'}</span>
}

function SectionHeading({ title, description }: { title: string; description?: string }) {
  return <div className="statistics-section-heading"><h2>{title}</h2>{description && <p>{description}</p>}</div>
}

export function CourseStatisticsPage() {
  usePageHeader({ title: 'Thống kê khóa học' })
  const [params, setParams] = useSearchParams()
  const courses = useQuery({ queryKey: ['statistics', 'courses', 'options'], queryFn: getAllOwnedCourses })
  const requested = params.get('course')
  const selected = courses.data?.find(course => course.id === requested)?.id ?? courses.data?.[0]?.id
  const stats = useQuery({ queryKey: ['statistics', 'course', selected], enabled: !!selected,
    queryFn: () => getCourseStats(selected!) })
  if (courses.isPending) return <LoadingState />
  if (courses.isError) return <ErrorState error={courses.error} onRetry={() => void courses.refetch()} />
  return <StatisticsLayout>
    <div className="statistics-toolbar">
      <UpdatedAt value={stats.data?.generated_at} />
      <div className="statistics-selector"><label htmlFor="statistics-course">Khóa học</label>
        <Select id="statistics-course" aria-label="Chọn khóa học" placeholder="Chọn khóa học" showSearch optionFilterProp="label"
          value={selected} onChange={value => setParams({ course: value })}
          options={courses.data.map(course => ({ label: course.title, value: course.id }))} />
      </div>
    </div>
    {!selected ? <Card><EmptyState description="Chưa có khóa học. Tạo khóa học để xem thống kê."
      action={<Link to={paths.teachingCourses}>Quản lý khóa học</Link>} /></Card>
      : stats.isPending ? <LoadingState />
        : stats.isError ? <ErrorState error={stats.error} onRetry={() => void stats.refetch()} />
          : <>
            <StatsSummary items={[
              { label: 'Học viên đã ghi danh', value: number(stats.data.enrolled_students) },
              { label: 'Số quiz đang xuất bản', value: number(stats.data.quiz_count) },
              { label: 'Lượt nộp bài', value: number(stats.data.submitted_attempts) },
              { label: 'Học viên hoàn thành', value: number(stats.data.completed_students) },
            ]} />
            <Card>
              <SectionHeading title="Tỷ lệ hoàn thành" />
              {stats.data.enrolled_students === 0
                ? <Alert type="info" showIcon title="Khóa học chưa có học viên ghi danh nên tỷ lệ hoàn thành là 0%." />
                : stats.data.quiz_count === 0
                  ? <Alert type="info" showIcon title="Khóa học chưa có quiz nào được xuất bản nên tỷ lệ hoàn thành là 0%." />
                  : <p className="statistics-muted">{number(stats.data.completed_students)} trên {number(stats.data.enrolled_students)} học viên đã ghi danh</p>}
              <div className="statistics-completion">
                <Tooltip title={`${number(stats.data.completed_students)} / ${number(stats.data.enrolled_students)} học viên hoàn thành`}>
                  <div role="img" aria-label={`Tỷ lệ hoàn thành ${formatScore(stats.data.completion_rate)}%. ${stats.data.completed_students} trên ${stats.data.enrolled_students} học viên.`}>
                    <Progress type="circle" percent={stats.data.completion_rate} size={168} strokeWidth={9}
                      strokeColor="var(--statistics-chart)" trailColor="var(--neutral-soft)"
                      format={value => <span className="statistics-circle-value">{formatScore(value ?? 0)}%<small>hoàn thành</small></span>} />
                  </div>
                </Tooltip>
                <dl className="statistics-completion-counts">
                  <div><dt><i className="statistics-swatch" />Đã hoàn thành</dt><dd>{number(stats.data.completed_students)} học viên</dd></div>
                  <div><dt><i className="statistics-swatch statistics-swatch-rest" />Chưa hoàn thành</dt><dd>{number(stats.data.enrolled_students - stats.data.completed_students)} học viên</dd></div>
                </dl>
              </div>
              <p className="statistics-note">Học viên hoàn thành khi đã nộp ít nhất một lần <b>mọi quiz đang xuất bản</b> của khóa ({number(stats.data.quiz_count)} quiz). Lượt nộp bài bao gồm cả quiz đã đóng.</p>
            </Card>
            <PublishedQuizzes key={selected} courseId={selected} quizCount={stats.data.quiz_count} />
          </>}
  </StatisticsLayout>
}

function PublishedQuizzes({ courseId, quizCount }: { courseId: string; quizCount: number }) {
  const quizzes = useQuery({ queryKey: ['statistics', 'published-quizzes', courseId], queryFn: () => getPublishedCourseQuizzes(courseId) })
  const rows = quizzes.data?.quizzes ?? []
  const aggregates = useQueries({ queries: rows.map(quiz => ({
    queryKey: ['statistics', 'quiz', quiz.id], queryFn: () => getQuizStats(quiz.id),
  })) })
  const aggregateById = new Map(rows.map((quiz, index) => [quiz.id, aggregates[index]]))
  return <Card>
    <SectionHeading title="Quiz của khóa" description={`${number(quizCount)} quiz đang xuất bản · Điểm trung bình trên thang 100, chỉ tính lượt đã nộp`} />
    {quizzes.isPending ? <LoadingState tip="Đang tải quiz của khóa…" />
      : quizzes.isError ? <ErrorState error={quizzes.error} onRetry={() => void quizzes.refetch()} />
        : <>
          {quizzes.data.errors.map(failure => <div key={failure.lessonId} className="statistics-partial-error">
            <p>Không tải được danh sách quiz của bài: <b>{failure.lessonTitle}</b>. Bảng bên dưới có thể chưa đầy đủ.</p>
            <ErrorState error={failure.error} onRetry={() => void quizzes.refetch()} />
          </div>)}
          {aggregates.some(result => result.isError) && <Alert type="warning" showIcon title="Một số thống kê quiz chưa tải được. Dữ liệu lỗi không được tính là 0." />}
          {!rows.length ? (!quizzes.data.errors.length && <EmptyState description="Chưa có quiz xuất bản. Xuất bản quiz trong bài học để xem thống kê tại đây."
            action={<Link to={paths.teachingCourseLessons(courseId)}>Quản lý bài học</Link>} />)
            : <Table rowKey="id" dataSource={rows} scroll={{ x: 780 }} pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
              columns={[
                { title: 'Tên quiz', dataIndex: 'title', render: value => <strong>{value}</strong> },
                { title: 'Bài học', dataIndex: 'lessonTitle' },
                { title: 'Lượt nộp', key: 'submitted', render: (_, row) => {
                  const result = aggregateById.get(row.id)
                  return result?.isPending ? 'Đang tải…' : result?.isError
                    ? <button className="statistics-retry" onClick={() => void result.refetch()}>Thử lại</button>
                    : result?.data ? number(result.data.submitted_attempts) : '—'
                } },
                { title: 'Điểm trung bình', key: 'average', render: (_, row) => {
                  const result = aggregateById.get(row.id)
                  return result?.isPending ? 'Đang tải…' : result?.isError ? 'Không tải được' : formatScore(result?.data?.average_score ?? null)
                } },
                { title: 'Hành động', key: 'action', render: (_, row) => <Link to={`${paths.quizStatistics(row.id)}?course=${encodeURIComponent(courseId)}`}>Xem chi tiết</Link> },
              ]} />}
          {rows.map(quiz => {
            const result = aggregateById.get(quiz.id)
            return result?.isError ? <div className="statistics-partial-error" key={quiz.id}>
              <p>Không tải được thống kê: <b>{quiz.title}</b>.</p>
              <ErrorState error={result.error} onRetry={() => void result.refetch()} />
            </div> : null
          })}
          {!!rows.length && <p className="statistics-note">—: chưa có điểm trung bình (không thay bằng 0). Mỗi quiz thống kê tất cả lượt đã nộp, không chỉ lượt tốt nhất.</p>}
        </>}
  </Card>
}

export function QuizStatisticsPage() {
  const { quizId = '' } = useParams()
  const [params] = useSearchParams()
  const courseId = params.get('course')
  const back = courseId ? `${paths.teachingStatistics}?course=${encodeURIComponent(courseId)}` : paths.teachingStatistics
  const stats = useQuery({ queryKey: ['statistics', 'quiz', quizId], queryFn: () => getQuizStats(quizId), enabled: !!quizId })
  const detail = useQuery({ queryKey: quizKeys.detail(quizId), queryFn: () => getQuiz(quizId), enabled: !!quizId })
  usePageHeader({ title: detail.data?.title ?? 'Thống kê quiz', crumbs: [{ label: 'Thống kê khóa học', to: back }, { label: detail.data?.title ?? 'Thống kê quiz' }] })
  if (stats.isPending) return <LoadingState />
  if (stats.isError) return <ErrorState error={stats.error} onRetry={() => void stats.refetch()} />
  const data = stats.data
  const hardest = [...data.hardest_questions].sort((a, b) => b.wrong_count - a.wrong_count)
  const questionLabel = (id: string) => {
    const question = detail.data?.questions.find(item => item.id === String(id))
    return question ? `Câu ${question.orderIndex + 1}: ${question.content}` : `Mã câu hỏi: ${id}`
  }
  return <StatisticsLayout>
    <div className="statistics-toolbar"><Link to={back}>← Thống kê khóa học</Link><UpdatedAt value={data.generated_at} /></div>
    <div className="statistics-quiz-context">
      <h2>{detail.data?.title ?? `Quiz ${quizId}`}</h2>
      {detail.data && <><Tag>{detail.data.status}</Tag><span className="statistics-muted">{number(detail.data.questions.length)} câu hỏi</span></>}
    </div>
    {detail.isPending && <LoadingState tip="Đang tải nội dung quiz…" />}
    {detail.isError && <Card><p>Không tải được nội dung quiz. Các số liệu bên dưới vẫn theo mã quiz/câu hỏi.</p><ErrorState error={detail.error} onRetry={() => void detail.refetch()} /></Card>}
    <StatsSummary items={[
      { label: 'Lượt nộp bài', value: number(data.submitted_attempts) },
      { label: 'Học viên đã nộp', value: number(data.unique_students) },
      { label: 'Điểm trung bình', value: <>{formatScore(data.average_score)} <small>/ 100</small></>, detail: 'Tính trên tất cả lượt đã nộp' },
    ]} />
    {data.submitted_attempts === 0 ? <Card><EmptyState description="Chưa có lượt nộp. Khi học viên nộp bài, thống kê quiz sẽ xuất hiện tại đây." /></Card>
      : <>
        <Card>
          <SectionHeading title="Câu bị sai nhiều nhất" description="5 câu có nhiều lượt sai nhất · Câu bỏ trống được tính là sai" />
          {!hardest.length ? <EmptyState description="Chưa ghi nhận câu trả lời sai hoặc bỏ trống trong các lượt đã nộp." />
            : <div className="statistics-bars">{hardest.slice(0, 5).map(question => <div className="statistics-bar-row" key={question.question_id}>
              <span>{questionLabel(question.question_id)}</span>
              <Tooltip title={`${question.wrong_count} lượt sai / ${data.submitted_attempts} lượt nộp`}>
                <div role="img" aria-label={`${questionLabel(question.question_id)}: ${question.wrong_count} lượt sai trên ${data.submitted_attempts} lượt nộp`}>
                  <Progress percent={question.wrong_count / data.submitted_attempts * 100} showInfo={false} size="small" strokeLinecap="butt"
                    strokeColor="var(--statistics-chart)" trailColor="var(--neutral-soft)" />
                </div>
              </Tooltip>
              <strong>{number(question.wrong_count)} <small className="statistics-muted">lượt sai</small></strong>
            </div>)}</div>}
          {!!hardest.length && <details className="statistics-data-table"><summary>Xem dữ liệu câu trả lời sai</summary>
            <Table rowKey="question_id" dataSource={hardest} scroll={{ x: 480 }} pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }} columns={[
              { title: 'Câu hỏi', dataIndex: 'question_id', render: id => questionLabel(id) },
              { title: 'Mã câu hỏi', dataIndex: 'question_id' },
              { title: 'Lượt sai (gồm bỏ trống)', dataIndex: 'wrong_count' },
            ]} />
          </details>}
        </Card>
        <Card>
          <SectionHeading title="Điểm cao nhất theo học viên" description="Lượt có điểm cao nhất của mỗi học viên · Hiển thị mã học viên do API thống kê cung cấp" />
          <Table rowKey="student_id" dataSource={data.best_scores} scroll={{ x: 420 }} pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
            locale={{ emptyText: <EmptyState description="Chưa có điểm cao nhất theo học viên." /> }} columns={[
              { title: 'Mã học viên', dataIndex: 'student_id' },
              { title: 'Điểm cao nhất / 100', dataIndex: 'score', render: value => <strong>{formatScore(value)}</strong> },
            ]} />
        </Card>
      </>}
  </StatisticsLayout>
}

export function SystemStatisticsPage() {
  usePageHeader({ title: 'Thống kê hệ thống' })
  const stats = useQuery({ queryKey: ['statistics', 'system'], queryFn: getSystemStats })
  if (stats.isPending) return <LoadingState />
  if (stats.isError) return <ErrorState error={stats.error} onRetry={() => void stats.refetch()} />
  const data = stats.data
  const definitions = [
    { label: 'Tài khoản đang hoạt động', value: data.active_users, detail: 'Bao gồm tài khoản Admin', definition: 'Tất cả tài khoản có trạng thái hoạt động, gồm Học viên, Giảng viên và Admin.' },
    { label: 'Giảng viên', value: data.teachers, detail: 'Gồm cả tài khoản bị khóa', definition: 'Tất cả tài khoản có vai trò TEACHER, không lọc theo trạng thái hoạt động.' },
    { label: 'Khóa học đang xuất bản', value: data.published_courses, detail: 'Không gồm khóa đã lưu trữ', definition: 'Khóa học đang được xuất bản và chưa được lưu trữ.' },
    { label: 'Lượt ghi danh', value: data.enrollments, detail: 'Trên toàn hệ thống', definition: 'Tổng số bản ghi ghi danh vào các khóa học; một học viên có thể ghi danh nhiều khóa.' },
    { label: 'Lượt nộp bài', value: data.submitted_attempts, detail: 'Chỉ tính trạng thái SUBMITTED', definition: 'Tất cả lượt làm quiz đã nộp trên toàn hệ thống, không tính lượt đang làm.' },
  ]
  return <StatisticsLayout>
    <UpdatedAt value={data.generated_at} />
    <StatsSummary items={definitions.map(item => ({ ...item, value: number(item.value) }))} />
    <Card>
      <SectionHeading title="Phân bố vai trò" description="Chưa có dữ liệu phân tách người dùng đang hoạt động theo vai trò" />
      <Alert type="info" showIcon title="Chưa thể hiển thị tỷ lệ Giảng viên / Học viên chính xác."
        description="API hiện trả tổng tài khoản hoạt động (gồm Admin) và tổng giảng viên (gồm tài khoản bị khóa). Hai số này không cùng phạm vi, nên không thể trừ để suy ra số học viên hoặc vẽ biểu đồ tỷ lệ." />
    </Card>
    <Card>
      <SectionHeading title="Cách tính số liệu" description="Số liệu tổng tại thời điểm cập nhật, không chia theo thời gian" />
      <dl className="statistics-definitions">{definitions.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.definition}</dd></div>)}</dl>
    </Card>
  </StatisticsLayout>
}
