import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'

const vite = await createServer({
  root: new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

try {
  const { formatDate, formatDateTime } = await vite.ssrLoadModule('/src/shared/utils/format.ts')

  test('formatDateTime converts UTC Z timestamp to Asia/Ho_Chi_Minh regardless of host TZ', () => {
    assert.equal(formatDateTime('2026-11-16T04:00:00Z'), '16/11/2026 11:00')
    assert.equal(formatDate('2026-11-16T04:00:00Z'), '16/11/2026')
  })

  test('formatDateTime handles day, month, and year rollovers across UTC -> VN (+7)', () => {
    assert.equal(formatDateTime('2026-11-16T20:00:00Z'), '17/11/2026 03:00')
    assert.equal(formatDateTime('2026-11-30T18:30:00Z'), '01/12/2026 01:30')
    assert.equal(formatDateTime('2026-12-31T17:00:00Z'), '01/01/2027 00:00')
  })

  test('formatDateTime handles explicit numeric offsets accurately', () => {
    assert.equal(formatDateTime('2026-11-16T10:00:00+02:00'), '16/11/2026 15:00')
    assert.equal(formatDateTime('2026-11-16T20:00:00-05:00'), '17/11/2026 08:00')
  })

  test('date-only strings never shift day by timezone', () => {
    assert.equal(formatDate('2026-11-16'), '16/11/2026')
    assert.equal(formatDateTime('2026-11-16'), '16/11/2026')
    assert.equal(formatDate('2026-02-30'), '—')
  })

  test('null, empty, invalid, and un-zoned strings return fallback without guessing UTC', () => {
    assert.equal(formatDateTime(null), '—')
    assert.equal(formatDateTime(undefined), '—')
    assert.equal(formatDateTime(''), '—')
    assert.equal(formatDateTime('not-a-date'), '—')
    assert.equal(formatDateTime('2026-11-16T04:00:00'), '—')
    assert.equal(formatDate(null), '—')
    assert.equal(formatDate('2026-11-16T04:00:00'), '—')
  })
} finally {
  await vite.close()
}
