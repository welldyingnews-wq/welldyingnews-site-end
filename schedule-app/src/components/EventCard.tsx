import type { Schedule } from '../types'
import { CATEGORY_COLOR_MAP } from '../constants'
import { formatDateTime } from '../utils/calendar'
import EventBadge from './EventBadge'

interface Props {
  schedule: Schedule
}

export default function EventCard({ schedule }: Props) {
  const color = CATEGORY_COLOR_MAP[schedule.category] || '#6B7280'
  const detailUrl = `/schedule/view/${schedule.id}`

  return (
    <a
      href={detailUrl}
      className="block bg-white rounded-lg border border-gray-200 p-4
        transition-all duration-200 ease-out hover:-translate-y-1 hover:shadow-lg hover:border-[#5e1985]/20"
      style={{ borderLeft: `4px solid ${color}`, textDecoration: 'none' }}
    >
      <div className="flex items-start gap-3">
        {schedule.image_url && (
          <img
            src={schedule.image_url}
            alt={schedule.title}
            className="w-20 h-16 object-cover rounded shrink-0 transition-transform duration-200 hover:scale-105"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <EventBadge category={schedule.category} size="md" />
          </div>
          <h4 className="text-sm font-semibold text-gray-800 mb-1 leading-snug hover:text-[#5e1985] transition-colors">
            {schedule.title}
          </h4>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
            <span>
              <i className="fa-regular fa-clock mr-1" />
              {formatDateTime(schedule.event_date)}
              {schedule.end_date && ` ~ ${formatDateTime(schedule.end_date)}`}
            </span>
            {schedule.location && (
              <span>
                <i className="fa-solid fa-location-dot mr-1" />
                {schedule.location}
              </span>
            )}
          </div>
          {schedule.description && (
            <p className="text-xs text-gray-500 mt-2 leading-relaxed line-clamp-2">
              {schedule.description}
            </p>
          )}
        </div>
      </div>
    </a>
  )
}
