const lunarFormatter = new Intl.DateTimeFormat('zh-CN-u-ca-chinese', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
})

const hourFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Shanghai',
  hour: 'numeric',
  hourCycle: 'h23',
})

const gregorianFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

const branches = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
const dayDigits = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九']

function lunarDay(day) {
  if (day <= 10) return `初${day === 10 ? '十' : dayDigits[day]}`
  if (day < 20) return `十${dayDigits[day - 10]}`
  if (day === 20) return '二十'
  if (day < 30) return `廿${dayDigits[day - 20]}`
  return '三十'
}

export function formatLunarTimestamp(createdAt) {
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return '时间读取失败'

  try {
    if (lunarFormatter.resolvedOptions().calendar !== 'chinese') return '时间读取失败'
    const dateParts = Object.fromEntries(lunarFormatter.formatToParts(date).map(({ type, value }) => [type, value]))
    const hourPart = hourFormatter.formatToParts(date).find(({ type }) => type === 'hour')?.value
    const day = Number(dateParts.day)
    const hour = Number(hourPart)
    if (!/^[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]$/.test(dateParts.yearName)
      || !dateParts.month?.endsWith('月') || !Number.isInteger(day) || day < 1 || day > 30
      || !Number.isInteger(hour) || hour < 0 || hour > 23) return '时间读取失败'

    const branch = branches[Math.floor(((hour + 1) % 24) / 2)]
    return `${dateParts.yearName}${dateParts.month}${lunarDay(day)} · ${branch}时`
  } catch {
    return '时间读取失败'
  }
}

export function formatGregorianTimestamp(createdAt) {
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return '时间读取失败'
  const parts = Object.fromEntries(gregorianFormatter.formatToParts(date).map(({ type, value }) => [type, value]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`
}
