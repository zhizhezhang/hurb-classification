import test from 'node:test'
import assert from 'node:assert/strict'
import { formatLunarTimestamp } from '../src/utils/lunarTime.js'

test('Spring Festival changes the lunar year at Beijing midnight', () => {
  assert.equal(formatLunarTimestamp('2026-02-16T15:59:00+00:00'), '乙巳腊月廿九 · 子时')
  assert.equal(formatLunarTimestamp('2026-02-16T16:00:00+00:00'), '丙午正月初一 · 子时')
})

test('leap lunar month remains distinct', () => {
  assert.equal(formatLunarTimestamp('2025-07-24T16:00:00+00:00'), '乙巳闰六月初一 · 子时')
})

test('lunar day names cover the tenth, eleventh, twentieth, twenty-first and thirtieth', () => {
  const cases = [
    ['2026-10-19T04:00:00+00:00', '初十'],
    ['2026-10-20T04:00:00+00:00', '十一'],
    ['2026-10-29T04:00:00+00:00', '二十'],
    ['2026-10-30T04:00:00+00:00', '廿一'],
    ['2026-11-08T04:00:00+00:00', '三十'],
  ]
  for (const [utcTime, lunarDay] of cases) {
    assert.equal(formatLunarTimestamp(utcTime), `丙午九月${lunarDay} · 午时`)
  }
})

test('09:00, 11:00, and 23:00 Beijing hour boundaries', () => {
  assert.equal(formatLunarTimestamp('2026-10-29T00:59:00+00:00'), '丙午九月二十 · 辰时')
  assert.equal(formatLunarTimestamp('2026-10-29T01:00:00+00:00'), '丙午九月二十 · 巳时')
  assert.equal(formatLunarTimestamp('2026-10-29T03:00:00+00:00'), '丙午九月二十 · 午时')
  assert.equal(formatLunarTimestamp('2026-10-29T15:00:00+00:00'), '丙午九月二十 · 子时')
  assert.equal(formatLunarTimestamp('2026-10-29T16:00:00+00:00'), '丙午九月廿一 · 子时')
})

test('invalid source time never masquerades as a lunar date', () => {
  assert.equal(formatLunarTimestamp('invalid'), '时间读取失败')
})
