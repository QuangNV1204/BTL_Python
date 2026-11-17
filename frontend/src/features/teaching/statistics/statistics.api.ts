import { apiGet } from '../../../shared/api/client'
import type { Page } from '../../../shared/api/types'
import { listOwnedCourses } from '../../marketplace/course.api'
import { getCourseLessons } from '../lessons/lesson.api'
import { getLessonQuizzes } from '../quizzes/quiz.api'
import type { QuizSummaryItem } from '../quizzes/quiz.types'

export interface CourseStats {
  enrolled_students: number
  quiz_count: number
  submitted_attempts: number
  completed_students: number
  completion_rate: number
  generated_at: string
}
export interface QuizStats {
  submitted_attempts: number
  unique_students: number
  average_score: number | null
  generated_at: string
  best_scores: { student_id: string; score: number | null }[]
  hardest_questions: { question_id: string; wrong_count: number }[]
}
export interface SystemStats {
  active_users: number
  teachers: number
  // Optional while an older backend is deployed; absent is not the same as zero.
  active_teachers?: number
  active_students?: number
  published_courses: number
  enrollments: number
  submitted_attempts: number
  generated_at: string
}
export interface PublishedQuizRow extends QuizSummaryItem { lessonTitle: string }

/** Follow server pagination, including a server-imposed page-size limit. */
export async function collectPages<T>(fetchPage: (page: number) => Promise<Page<T>>): Promise<T[]> {
  const items: T[] = []
  let page = 1
  while (true) {
    const result = await fetchPage(page)
    if (result.page !== page) throw new Error('Phân trang không tiến lên. Vui lòng tải lại danh sách.')
    items.push(...result.items)
    if (items.length >= result.total) return items
    if (!result.items.length) throw new Error('Danh sách đã thay đổi trong khi tải. Vui lòng thử lại.')
    page += 1
  }
}

/** Keep independent failures visible without discarding successfully loaded rows. */
export async function mapSettledBounded<T, R>(items: T[], work: (item: T) => Promise<R>, concurrency = 4) {
  const results: PromiseSettledResult<R>[] = new Array(items.length)
  let next = 0
  await Promise.all(Array.from({ length: Math.min(Math.max(1, concurrency), items.length) }, async () => {
    while (next < items.length) {
      const index = next++
      try { results[index] = { status: 'fulfilled', value: await work(items[index]) } }
      catch (reason) { results[index] = { status: 'rejected', reason } }
    }
  }))
  return results
}

export const getAllOwnedCourses = () => collectPages(page => listOwnedCourses({ page, page_size: 100 }))
export const getCourseStats = (id: string) => apiGet<CourseStats>(`/statistics/courses/${id}`)
export const getQuizStats = (id: string) => apiGet<QuizStats>(`/statistics/quizzes/${id}`)
export const getSystemStats = () => apiGet<SystemStats>('/statistics/system')

export async function getPublishedCourseQuizzes(courseId: string) {
  const lessons = await getCourseLessons(courseId)
  const results = await mapSettledBounded(lessons, async lesson => {
    const quizzes = await collectPages(page => getLessonQuizzes(lesson.id, page, 100))
    return quizzes.filter(quiz => quiz.status === 'PUBLISHED').map(quiz => ({ ...quiz, lessonTitle: lesson.title }))
  })
  const quizzes: PublishedQuizRow[] = []
  const errors: { lessonId: string; lessonTitle: string; error: unknown }[] = []
  results.forEach((result, index) => {
    if (result.status === 'fulfilled') quizzes.push(...result.value)
    else errors.push({ lessonId: lessons[index].id, lessonTitle: lessons[index].title, error: result.reason })
  })
  return { quizzes, errors }
}

export function activeRoleBreakdown(data: Pick<SystemStats, 'active_teachers' | 'active_students'>) {
  const teachers = data.active_teachers
  const students = data.active_students
  if (teachers == null || students == null || !Number.isSafeInteger(teachers) ||
    !Number.isSafeInteger(students) || teachers < 0 || students < 0) return null
  const total = teachers + students
  if (!Number.isSafeInteger(total)) return null
  return { teachers, students, total, teacherPercent: total ? teachers * 100 / total : 0 }
}

export function formatScore(score: number | null): string {
  return score == null ? '—' : score.toLocaleString('vi-VN', { maximumFractionDigits: 2 })
}
