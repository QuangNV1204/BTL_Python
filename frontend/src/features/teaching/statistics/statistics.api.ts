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
export interface QuizResultRow extends QuizSummaryItem { lessonTitle: string }

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) {
    if (signal.throwIfAborted) signal.throwIfAborted()
    throw new DOMException('Đã hủy tải dữ liệu.', 'AbortError')
  }
}

/** Follow stable server pagination, including a server-imposed page-size limit. */
export async function collectPages<T>(fetchPage: (page: number) => Promise<Page<T>>, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = []
  const ids = new Set<string>()
  let total: number | undefined
  let pageSize: number | undefined
  let page = 1
  while (true) {
    throwIfAborted(signal)
    const result = await fetchPage(page)
    throwIfAborted(signal)
    if (result.page !== page) throw new Error('Phân trang không tiến lên. Vui lòng tải lại danh sách.')
    total ??= result.total
    pageSize ??= result.page_size
    if (!Number.isSafeInteger(total) || total < 0 || !Number.isSafeInteger(pageSize) || pageSize <= 0 ||
      result.total !== total || result.page_size !== pageSize ||
      result.items.length !== Math.min(pageSize, total - items.length)) {
      throw new Error('Danh sách đã thay đổi trong khi tải. Vui lòng thử lại.')
    }
    for (const item of result.items) {
      if (item != null && typeof item === 'object' && 'id' in item && item.id != null) {
        const id = String(item.id)
        if (ids.has(id)) throw new Error('Danh sách đã thay đổi trong khi tải (trùng mã). Vui lòng thử lại.')
        ids.add(id)
      }
    }
    // Check non-progress before completion; a shrinking total must never hide missing rows.
    if (!result.items.length && items.length < total) {
      throw new Error('Danh sách đã thay đổi trong khi tải. Vui lòng thử lại.')
    }
    items.push(...result.items)
    if (items.length === total) return items
    page += 1
  }
}

/** Keep independent failures visible, but never turn cancellation into a partial failure. */
export async function mapSettledBounded<T, R>(items: T[], work: (item: T) => Promise<R>, concurrency = 4, signal?: AbortSignal) {
  throwIfAborted(signal)
  const results: PromiseSettledResult<R>[] = new Array(items.length)
  let next = 0
  let cancelled = false
  await Promise.all(Array.from({ length: Math.min(Math.max(1, concurrency), items.length) }, async () => {
    while (next < items.length) {
      throwIfAborted(signal)
      if (cancelled) throw new DOMException('Đã hủy tải dữ liệu.', 'AbortError')
      const index = next++
      try {
        const value = await work(items[index])
        throwIfAborted(signal)
        results[index] = { status: 'fulfilled', value }
      } catch (reason) {
        if (signal?.aborted || (reason instanceof Error && reason.name === 'AbortError')) {
          cancelled = true
          throwIfAborted(signal)
          throw reason
        }
        results[index] = { status: 'rejected', reason }
      }
    }
  }))
  throwIfAborted(signal)
  return results
}

export const getAllOwnedCourses = (signal?: AbortSignal) =>
  collectPages(page => listOwnedCourses({ page, page_size: 100 }, signal), signal)
export const getCourseStats = (id: string, signal?: AbortSignal) => apiGet<CourseStats>(`/statistics/courses/${id}`, { signal })
export const getQuizStats = (id: string, signal?: AbortSignal) => apiGet<QuizStats>(`/statistics/quizzes/${id}`, { signal })
export const getSystemStats = (signal?: AbortSignal) => apiGet<SystemStats>('/statistics/system', { signal })

/** Request only the visible page; results remain paired with IDs even after independent failures. */
export async function getQuizPageStats(quizzes: Pick<QuizSummaryItem, 'id'>[], page: number, pageSize: number, signal?: AbortSignal) {
  const visible = quizzes.slice((page - 1) * pageSize, page * pageSize)
  const results = await mapSettledBounded(visible, quiz => getQuizStats(quiz.id, signal), 4, signal)
  return visible.map((quiz, index) => ({ quizId: quiz.id, result: results[index] }))
}

export async function getCourseResultQuizzes(courseId: string, signal?: AbortSignal) {
  throwIfAborted(signal)
  const lessons = await getCourseLessons(courseId, signal)
  const results = await mapSettledBounded(lessons, async lesson => {
    const quizzes = await collectPages(page => getLessonQuizzes(lesson.id, page, 100, signal), signal)
    return quizzes.filter(quiz => quiz.status === 'PUBLISHED' || quiz.status === 'CLOSED')
      .map(quiz => ({ ...quiz, lessonTitle: lesson.title }))
  }, 4, signal)
  const quizzes: QuizResultRow[] = []
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
