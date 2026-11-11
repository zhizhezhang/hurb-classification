export function maxHistoryStart(total, visibleCount) {
  return total > 4 ? Math.max(0, total - visibleCount) : 0
}

export function moveHistoryStart(start, direction, total, visibleCount) {
  const maximum = maxHistoryStart(total, visibleCount)
  return Math.min(maximum, Math.max(0, start + direction))
}
