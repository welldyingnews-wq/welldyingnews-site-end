import type { Schedule } from '../types'
import { getCalendarWeeks, toDateKey } from '../utils/calendar'
import { DAY_NAMES } from '../constants'
import CalendarDay from './CalendarDay'

interface Props {
  year: number
  month: number
  schedules: Schedule[]
  selectedDate: string | null
  onSelectDate: (dateKey: string) => void
  onPrevMonth: () => void
  onNextMonth: () => void
}

export default function Calendar({
  year, month, schedules, selectedDate,
  onSelectDate, onPrevMonth, onNextMonth
}: Props) {
  const weeks = getCalendarWeeks(year, month)

  // Group schedules by day
  const byDay: Record<number, Schedule[]> = {}
  for (const s of schedules) {
    const d = new Date(s.event_date)
    if (d.getFullYear() === year && d.getMonth() + 1 === month) {
      const day = d.getDate()
      if (!byDay[day]) byDay[day] = []
      byDay[day].push(s)
    }
  }

  return (
    <div>
      {/* Month Navigation */}
      <div className="flex items-center justify-center gap-4 mb-4">
        <button
          onClick={onPrevMonth}
          className="w-8 h-8 flex items-center justify-center rounded-full border border-gray-300 hover:bg-gray-100 transition-colors"
        >
          <i className="fa-solid fa-chevron-left text-xs text-gray-600" />
        </button>
        <h2 className="text-lg font-bold text-gray-800">
          {year}년 {month}월
        </h2>
        <button
          onClick={onNextMonth}
          className="w-8 h-8 flex items-center justify-center rounded-full border border-gray-300 hover:bg-gray-100 transition-colors"
        >
          <i className="fa-solid fa-chevron-right text-xs text-gray-600" />
        </button>
      </div>

      <p className="text-xs text-gray-400 text-center mb-3">
        <i className="fa-regular fa-hand-pointer mr-1" />
        날짜를 클릭하면 하단에서 해당일 일정을 확인하실 수 있습니다
      </p>

      {/* Calendar Table */}
      <table className="w-full border-collapse table-fixed">
        <thead>
          <tr>
            {DAY_NAMES.map((name, i) => (
              <th
                key={name}
                className={`py-2 text-xs font-semibold text-center border-b-2 border-gray-200
                  ${i === 0 ? 'text-red-400' : i === 6 ? 'text-blue-400' : 'text-gray-500'}`}
              >
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, wi) => (
            <tr key={wi}>
              {week.map((day, di) => (
                <CalendarDay
                  key={di}
                  year={year}
                  month={month}
                  day={day}
                  events={day ? (byDay[day] || []) : []}
                  isSelected={day !== null && toDateKey(year, month, day) === selectedDate}
                  onSelect={(d) => onSelectDate(toDateKey(year, month, d))}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
