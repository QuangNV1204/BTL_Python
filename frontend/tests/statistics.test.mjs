import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

test('statistics pagination, bounded partial failures and null scores', async () => {
  const server = await createServer({ configFile: false, root: fileURLToPath(new URL('..', import.meta.url)),
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, ws: false }, appType: 'custom' })
  const oldFetch = globalThis.fetch
  try {
    const { collectPages, mapSettledBounded, getAllOwnedCourses, getCourseResultQuizzes, formatScore, activeRoleBreakdown } =
      await server.ssrLoadModule('/src/features/teaching/statistics/statistics.api.ts')
    const pages = []
    const items = await collectPages(async page => {
      pages.push(page)
      return { items: [page], total: 3, page, page_size: 1 }
    })
    assert.deepEqual(items, [1, 2, 3])
    assert.deepEqual(pages, [1, 2, 3])
    await assert.rejects(collectPages(async () => ({ items: [], total: 3, page: 1, page_size: 1 })), /đã thay đổi/)
    await assert.rejects(collectPages(async () => ({ items: [1], total: 3, page: 1, page_size: 1 })), /không tiến lên/)
    assert.equal(formatScore(null), '—')
    assert.equal(formatScore(0), '0')
    assert.equal(formatScore(75.25), '75,25')
    assert.deepEqual(activeRoleBreakdown({ active_teachers: 1, active_students: 2 }), { teachers: 1, students: 2, total: 3, teacherPercent: 100 / 3 })
    assert.deepEqual(activeRoleBreakdown({ active_teachers: 0, active_students: 0 }), { teachers: 0, students: 0, total: 0, teacherPercent: 0 })
    assert.equal(activeRoleBreakdown({ active_teachers: 2, active_students: 0 }).teacherPercent, 100)
    assert.equal(activeRoleBreakdown({ active_teachers: 0, active_students: 2 }).teacherPercent, 0)
    for (const data of [{}, { active_teachers: 1 }, { active_teachers: -1, active_students: 2 }, { active_teachers: NaN, active_students: 2 }]) assert.equal(activeRoleBreakdown(data), null)

    let running = 0
    let maximum = 0
    const failure = new Error('partial failure')
    const settled = await mapSettledBounded([0, 1, 2, 3, 4, 5], async index => {
      running++
      maximum = Math.max(maximum, running)
      await new Promise(resolve => setTimeout(resolve, 1))
      running--
      if (index === 2) throw failure
      return index * 2
    }, 2)
    assert.equal(maximum, 2)
    assert.equal(settled[2].reason, failure)
    assert.equal(settled[5].value, 10)

    const requests = []
    globalThis.fetch = async input => {
      const url = new URL(input, 'http://localhost')
      requests.push(url.pathname + url.search)
      const page = Number(url.searchParams.get('page') ?? 1)
      let body
      if (url.pathname.endsWith('/teaching/courses')) {
        body = { items: [{ id: page, title: `Course ${page}` }], total: 2, page, page_size: 1 }
      } else if (url.pathname.endsWith('/courses/1/lessons')) {
        body = [{ id: '10', course_id: '1', title: 'Lesson A' }, { id: '11', course_id: '1', title: 'Lesson B' }]
      } else if (url.pathname.endsWith('/lessons/10/quizzes')) {
        body = { items: [{ id: String(page), lesson_id: '10', title: `Quiz ${page}`, status: page === 1 ? 'DRAFT' : 'PUBLISHED' }], total: 2, page, page_size: 1 }
      } else if (url.pathname.endsWith('/lessons/11/quizzes')) {
        return new Response(JSON.stringify({ message: 'Forbidden', code: 'FORBIDDEN' }), { status: 403, headers: { 'Content-Type': 'application/json' } })
      } else throw new Error(`Unexpected request ${url}`)
      return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
    }
    const courses = await getAllOwnedCourses()
    assert.deepEqual(courses.map(course => course.id), ['1', '2'])
    const result = await getCourseResultQuizzes('1')
    assert.equal(result.quizzes.length, 1)
    assert.equal(result.quizzes[0].id, '2')
    assert.equal(result.quizzes[0].lessonTitle, 'Lesson A')
    assert.equal(result.errors.length, 1)
    assert.equal(result.errors[0].error.status, 403)
    assert.ok(requests.some(url => url.includes('/lessons/10/quizzes?page=2')))
  } finally {
    globalThis.fetch = oldFetch
    await server.close()
  }
})
