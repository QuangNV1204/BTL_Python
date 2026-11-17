import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

test('statistics review regressions: drift, closed quizzes, page limits and abort', async () => {
  const server = await createServer({ configFile: false, root: fileURLToPath(new URL('..', import.meta.url)),
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, ws: false }, appType: 'custom' })
  const oldFetch = globalThis.fetch
  try {
    const { collectPages, mapSettledBounded, getCourseResultQuizzes, getQuizPageStats } =
      await server.ssrLoadModule('/src/features/teaching/statistics/statistics.api.ts')
    // Regression: total shrinks to accumulated count on an empty second page.
    await assert.rejects(collectPages(async page => page === 1
      ? { items: [{ id: 'a' }, { id: 'b' }], page, page_size: 2, total: 3 }
      : { items: [], page, page_size: 2, total: 2 }), /thay đổi/)
    await assert.rejects(collectPages(async page => ({ items: [{ id: 'same' }], page, page_size: 1, total: 2 })), /thay đổi/)
    await assert.rejects(collectPages(async page => ({ items: [{ id: String(page) }], page, page_size: page, total: 3 })), /thay đổi/)

    const aborted = new AbortController()
    aborted.abort()
    let calls = 0
    await assert.rejects(collectPages(async () => { calls++; return { items: [], total: 0, page: 1, page_size: 1 } }, aborted.signal), { name: 'AbortError' })
    assert.equal(calls, 0)
    const betweenPages = new AbortController()
    await assert.rejects(collectPages(async page => {
      calls++
      betweenPages.abort()
      return { items: [page], total: 2, page, page_size: 1 }
    }, betweenPages.signal), { name: 'AbortError' })
    assert.equal(calls, 1)

    const workers = new AbortController()
    const scheduled = []
    await assert.rejects(mapSettledBounded([0, 1, 2, 3], async item => {
      scheduled.push(item)
      workers.abort()
      return item
    }, 1, workers.signal), { name: 'AbortError' })
    assert.deepEqual(scheduled, [0])

    let running = 0, maximum = 0
    const requests = []
    let receivedSignal
    globalThis.fetch = async (input, init) => {
      const url = new URL(input, 'http://localhost')
      requests.push(url.pathname)
      receivedSignal = init?.signal
      if (url.pathname === '/courses/1/lessons' || url.pathname === '/api/v1/courses/1/lessons') {
        return Response.json([{ id: '11', course_id: '1', title: 'Lesson' }])
      }
      if (url.pathname.endsWith('/lessons/11/quizzes')) {
        return Response.json({ items: ['DRAFT', 'PUBLISHED', 'CLOSED'].map((status, i) => ({ id: String(i + 1), lesson_id: '11', title: status, status, question_count: 1 })), total: 3, page: 1, page_size: 100 })
      }
      assert.match(url.pathname, /\/statistics\/quizzes\/\d+$/)
      running++
      maximum = Math.max(maximum, running)
      await new Promise(resolve => setImmediate(resolve))
      running--
      return Response.json({ submitted_attempts: 1, unique_students: 1, average_score: 50, generated_at: '2026-01-01T00:00:00Z', best_scores: [], hardest_questions: [] })
    }
    const signal = new AbortController().signal
    const result = await getCourseResultQuizzes('1', signal)
    assert.deepEqual(result.quizzes.map(q => q.status), ['PUBLISHED', 'CLOSED'])
    assert.equal(receivedSignal, signal)
    requests.length = 0
    const all = Array.from({ length: 200 }, (_, i) => ({ id: String(i + 1) }))
    const page = await getQuizPageStats(all, 1, 10, signal)
    assert.equal(page.length, 10)
    assert.deepEqual(page.map(item => item.quizId), all.slice(0, 10).map(q => q.id))
    assert.equal(requests.length, 10)
    assert(maximum <= 4, `unbounded concurrency: ${maximum}`)
    assert.equal(receivedSignal, signal)
    requests.length = 0
    const next = await getQuizPageStats(all, 2, 10, signal)
    assert.deepEqual(next.map(item => item.quizId), all.slice(10, 20).map(q => q.id))
    assert.equal(requests.length, 10)
    requests.length = 0
    await assert.rejects(getQuizPageStats(all, 1, 10, aborted.signal), { name: 'AbortError' })
    assert.equal(requests.length, 0)
  } finally {
    globalThis.fetch = oldFetch
    await server.close()
  }
})
