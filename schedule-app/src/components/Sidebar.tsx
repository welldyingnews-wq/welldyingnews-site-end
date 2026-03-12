import type { Schedule } from '../types'
import { formatDate } from '../utils/calendar'
import EventBadge from './EventBadge'

interface Props {
  recent: Schedule[]
  selectedCategory: string | null
}

export default function Sidebar({ recent, selectedCategory }: Props) {
  const filteredRecent = selectedCategory
    ? recent.filter(s => s.category === selectedCategory)
    : recent

  return (
    <aside
      className="
        w-full lg:w-[350px] shrink-0 bg-white rounded-lg border border-gray-200
        overflow-y-auto max-h-[360px] lg:max-h-[calc(100vh-120px)]
      "
    >
      <div className="p-4">
        <h2 className="text-sm font-bold text-gray-800 flex items-center gap-1.5 mb-4">
          <i className="fa-regular fa-newspaper text-[#5e1985]" />
          최근 소식
          {selectedCategory && (
            <span className="text-xs font-normal text-[#5e1985]">
              — {selectedCategory}
            </span>
          )}
        </h2>

        {filteredRecent.length === 0 ? (
          <p className="text-xs text-gray-400 text-center py-6">
            등록된 일정이 없습니다.
          </p>
        ) : (
          <div className="space-y-0">
            {filteredRecent.map(s => {
              const detailUrl = `/schedule/view/${s.id}`
              return (
                <a
                  key={s.id}
                  href={detailUrl}
                  className="block py-3 border-b border-gray-100 last:border-0
                    hover:bg-gray-50 -mx-4 px-4 transition-colors"
                  style={{ textDecoration: 'none' }}
                >
                  <div className="flex gap-2.5">
                    {/* Thumbnail - only show when image exists */}
                    {s.image_url && (
                      <img
                        src={s.image_url}
                        alt={s.title}
                        className="w-16 h-12 object-cover rounded shrink-0"
                      />
                    )}
                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="mb-1">
                        <EventBadge category={s.category} size="sm" />
                      </div>
                      <p className="text-[13px] font-medium text-gray-700 leading-snug line-clamp-2 hover:text-[#5e1985] transition-colors">
                        {s.title}
                      </p>
                      <div className="text-[11px] text-gray-400 flex items-center gap-1 mt-1">
                        <i className="fa-regular fa-calendar" />
                        {formatDate(s.event_date)}
                      </div>
                    </div>
                  </div>
                </a>
              )
            })}
          </div>
        )}
      </div>
    </aside>
  )
}
