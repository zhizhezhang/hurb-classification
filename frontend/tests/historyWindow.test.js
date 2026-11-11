import test from 'node:test'
import assert from 'node:assert/strict'
import { maxHistoryStart, moveHistoryStart } from '../src/utils/historyWindow.js'

test('three and four records stay in one window without navigation', () => {
  for (const total of [3, 4]) {
    assert.equal(maxHistoryStart(total, 4), 0)
    assert.equal(moveHistoryStart(0, 1, total, 4), 0)
  }
})

test('five records move 1234 → 2345 → 1234', () => {
  assert.equal(maxHistoryStart(5, 4), 1)
  assert.equal(moveHistoryStart(0, 1, 5, 4), 1)
  assert.equal(moveHistoryStart(1, -1, 5, 4), 0)
  assert.equal(moveHistoryStart(1, 1, 5, 4), 1)
})

test('six and ten records advance one item at a time and stop at the end', () => {
  for (const total of [6, 10]) {
    let start = 0
    for (let expected = 1; expected <= total - 4; expected++) {
      start = moveHistoryStart(start, 1, total, 4)
      assert.equal(start, expected)
    }
    assert.equal(moveHistoryStart(start, 1, total, 4), total - 4)
  }
})

test('narrow windows show two records when there are more than four', () => {
  assert.equal(maxHistoryStart(4, 2), 0)
  assert.equal(maxHistoryStart(5, 2), 3)
  assert.equal(moveHistoryStart(2, 1, 5, 2), 3)
})
