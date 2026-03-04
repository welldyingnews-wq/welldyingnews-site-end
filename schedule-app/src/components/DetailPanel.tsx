import type { Schedule } from '../types'
import EventCard from './EventCard'

interface Props {
  selectedDate: string | null
  schedules: Schedule[]
}

export default function DetailPanel({ selectedDate, schedules }: Props) {
  if (!selectedDate) {
    return (
      <div className="mt-6 p-8 text-center text-gray-400 text-sm border border-dashed border-gray-200 rounded-lg">
        <i className="fa-regular fa-calendar-check text-2xl mb-2 block" />
        날짜를 클릭하면 해당일의 일정을 확인할 수 있습니다.
      </div>
    )
  }

  // Parse selected date for display
  const [y, m, d] = selectedDate.split('-')
  const dateLabel = `${y}년 ${parseInt(m)}월 ${parseInt(d)}일`

  // Filter schedules for selected date
  const daySchedules = schedules.filter(s => {
    const dt = new Date(s.event_date)
    return (
      dt.getFullYear() === parseInt(y) &&
      dt.getMonth() + 1 === parseInt(m) &&
      dt.getDate() === parseInt(d)
    )
  })

  return (
    <div className="mt-6">
      <h3 className="text-base font-bold text-gray-800 mb-3 flex items-center gap-2">
        <i className="fa-regular fa-calendar-day text-[#5e1985]" />
        {dateLabel}
        <span className="text-sm font-normal text-gray-400">({daySchedules.length}건)</span>
      </h3>
      {daySchedules.length === 0 ? (
        <div className="p-6 text-center text-gray-400 text-sm bg-gray-50 rounded-lg">
          이 날짜에 등록된 일정이 없습니다.
        </div>
      ) : (
        <div className="grid gap-3">
          {daySchedules.map(s => (
            <EventCard key={s.id} schedule={s} />
          ))}
        </div>
      )}
    </div>
  )
}
