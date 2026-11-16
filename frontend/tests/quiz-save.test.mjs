import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const make = (id, index) => ({ id, content: `Q${id}`, order_index: index, options: [
  { content: 'A', is_correct: true, order_index: 0 }, { content: 'B', is_correct: false, order_index: 1 },
] })
const local = (q) => ({ id: q.id, content: q.content, orderIndex: q.order_index,
  options: q.options.map((o) => ({ content: o.content, isCorrect: o.is_correct, orderIndex: o.order_index })) })

for (const partial of [false, true]) {
  test(`save reordered/new questions twice without duplicates; partial failure=${partial}`, async () => {
    const original = globalThis.fetch
    const server = await createServer({ configFile: false, root: fileURLToPath(new URL('..', import.meta.url)),
      server: { middlewareMode: true, ws: false }, appType: 'custom' })
    let stored = [make('1', 0), make('2', 1)], nextId = 3, fail = partial
    try {
      globalThis.fetch = async (url, options) => {
        const body = options.body ? JSON.parse(options.body) : undefined
        const reply = (data, status = 200) => new Response(JSON.stringify(data), { status,
          headers: { 'Content-Type': 'application/json' } })
        if (options.method === 'GET') return reply({ id: '30', lesson_id: '10', title: 'Quiz', status: 'DRAFT', questions: stored })
        if (options.method === 'POST') {
          if (fail && nextId === 4) { fail = false; return reply({ message: 'injected failure' }, 500) }
          const q = { ...body, id: String(nextId++) }; stored.push(q); return reply(q)
        }
        const id = url.split('/').at(-1)
        if (options.method === 'DELETE') { stored = stored.filter((q) => q.id !== id); return new Response(null, { status: 204 }) }
        if (stored.some((q) => q.id !== id && q.order_index === body.order_index)) return reply({ message: 'duplicate index' }, 409)
        const q = { ...body, id }; stored = stored.map((old) => old.id === id ? q : old); return reply(q)
      }
      const { saveQuizDraft } = await server.ssrLoadModule('/src/features/teaching/quizzes/saveQuizDraft.ts')
      const draft = [local(stored[1]), local(stored[0]), local(make(undefined, 2)), local(make(undefined, 3))]
      const save = () => saveQuizDraft('30', 'Quiz', draft, [], (i, saved) => { draft[i] = saved }, () => {})
      if (partial) await assert.rejects(save(), /injected failure/)
      await save()
      await save()
      assert.equal(stored.length, 4)
      assert.equal(nextId, 5)
      assert.deepEqual([...stored].sort((a,b) => a.order_index-b.order_index).map((q) => q.id), ['2','1','3','4'])
      assert.ok(draft.every((q) => q.id))
    } finally { globalThis.fetch = original; await server.close() }
  })
}
