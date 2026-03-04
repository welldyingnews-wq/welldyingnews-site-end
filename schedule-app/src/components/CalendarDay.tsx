import { useState } from 'react'
import type { Schedule } from '../types'
import EventBadge from './EventBadge'
import { isToday } from '../utils/calendar'

interface Props {
  year: number
  month: number
  day: number | null
  events: Schedule[]
  isSelected: boolean
  onSelect: (day: number) => void
}

const MAX_VISIBLE = 3

export default function CalendarDay({ year, month, day, events, isSelected, onSelect }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (day === null) {
    return <td className="bg-gray-50 border border-gray-100 p-1 align-top h-[90px]" />
  }

  const today = isToday(year, month, day)
  const dow = new Date(year, month - 1, day).getDay()
  const isSun = dow === 0
  const isSat = dow === 6
  const visible = expanded ? events : events.slice(0, MAX_VISIBLE)
  const remaining = events.length - MAX_VISIBLE

  return (
    <td
      onClick={() => onSelect(day)}
      className={`border border-gray-200 p-1 align-top h-[90px] overflow-y-auto cursor-pointer
        transition-all duration-200 ease-out hover:scale-105 hover:z-10 hover:shadow-lg hover:border-[#5e1985]/30 relative
        ${isSelected ? 'bg-purple-50 ring-2 ring-[#5e1985] ring-inset' : 'hover:bg-white'}
        ${today ? 'bg-yellow-50' : ''}`}
    >
      <span className={`inline-flex items-center justify-center w-6 h-6 text-xs font-semibold rounded-full mb-0.5
        ${today ? 'bg-[#5e1985] text-white' : ''}
        ${isSun ? 'text-red-500' : ''}
        ${isSat ? 'text-blue-500' : ''}`}>
        {day}
      </span>
      <div className="space-y-0.5">
        {visible.map(ev => (
          <div key={ev.id} onClick={e => e.stopPropagation()}>
            <a href={`/schedule/view/${ev.id}`}
               className="flex items-center gap-1 hover:opacity-80">
              <EventBadge category={ev.category} size="sm" />
              <span className="text-[10px] text-gray-600 truncate leading-tight">{ev.title.slice(0, 10)}</span>
            </a>
          </div>
        ))}
        {!expanded && remaining > 0 && (
          <button
            onClick={e => { e.stopPropagation(); setExpanded(true) }}
            className="text-[10px] text-[#5e1985] hover:underline font-medium"
          >
            +{remaining}개 더보기
          </button>
        )}
        {expanded && events.length > MAX_VISIBLE && (
          <button
            onClick={e => { e.stopPropagation(); setExpanded(false) }}
            className="text-[10px] text-gray-400 hover:underline"
          >
            접기
          </button>
        )}
      </div>
    </td>
  )
}
