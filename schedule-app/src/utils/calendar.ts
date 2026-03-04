/** Build a 2D array of day numbers for a calendar month grid.
 *  Each inner array has 7 entries (Sun–Sat). null = empty cell.
 */
export function getCalendarWeeks(year: number, month: number): (number | null)[][] {
  const firstDay = new Date(year, month - 1, 1)
  const daysInMonth = new Date(year, month, 0).getDate()
  const startDow = firstDay.getDay() // 0=Sun

  const weeks: (number | null)[][] = []
  let week: (number | null)[] = []

  for (let i = 0; i < startDow; i++) week.push(null)

  for (let day = 1; day <= daysInMonth; day++) {
    week.push(day)
    if (week.length === 7) {
      weeks.push(week)
      week = []
    }
  }

  if (week.length > 0) {
    while (week.length < 7) week.push(null)
    weeks.push(week)
  }

  return weeks
}

/** Format: "2026-03-15" */
export function toDateKey(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/** "14:00" from ISO datetime string */
export function formatTime(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** "2026.03.15" from ISO datetime string */
export function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`
}

/** "2026.03.15 14:00" from ISO datetime string */
export function formatDateTime(iso: string): string {
  return `${formatDate(iso)} ${formatTime(iso)}`
}

export function isToday(year: number, month: number, day: number): boolean {
  const now = new Date()
  return now.getFullYear() === year && now.getMonth() + 1 === month && now.getDate() === day
}
