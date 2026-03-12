import { useState, useMemo, useCallback } from 'react'
import { useSchedules } from './hooks/useSchedules'
import Sidebar from './components/Sidebar'
import CategoryTabs from './components/CategoryTabs'
import Calendar from './components/Calendar'
import DetailPanel from './components/DetailPanel'
import EventCard from './components/EventCard'
import type { Schedule } from './types'

export default function App() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const { schedules, recent, loading } = useSchedules(year, month)

  // Search state
  const [searchInput, setSearchInput] = useState('')
  const [searchWord, setSearchWord] = useState('')
  const [searchResults, setSearchResults] = useState<Schedule[]>([])
  const [searching, setSearching] = useState(false)

  // Filter by selected category
  const filtered = useMemo(() => {
    if (!selectedCategory) return schedules
    return schedules.filter(s => s.category === selectedCategory)
  }, [schedules, selectedCategory])

  const handlePrevMonth = () => {
    setSelectedDate(null)
    if (month === 1) { setYear(y => y - 1); setMonth(12) }
    else setMonth(m => m - 1)
  }

  const handleNextMonth = () => {
    setSelectedDate(null)
    if (month === 12) { setYear(y => y + 1); setMonth(1) }
    else setMonth(m => m + 1)
  }

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    const word = searchInput.trim()
    if (!word) {
      setSearchWord('')
      setSearchResults([])
      return
    }
    setSearching(true)
    setSearchWord(word)
    try {
      const res = await fetch(`/api/schedules/search?q=${encodeURIComponent(word)}`)
      if (res.ok) {
        const data = await res.json()
        setSearchResults(data.results || [])
      }
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }, [searchInput])

  const clearSearch = () => {
    setSearchInput('')
    setSearchWord('')
    setSearchResults([])
  }

  return (
    <div className="font-sans">
      {/* Page Header */}
      <div className="mb-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-gray-800 flex items-center gap-2">
              <i className="fa-regular fa-calendar text-[#5e1985]" />
              주요일정
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              웰다잉 관련 세미나, 학술대회, 행사 일정을 안내합니다.
            </p>
          </div>
          {/* Actions */}
          <div className="flex items-center gap-2 flex-wrap">
          <a
            href="/com/schedule-request.html"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 h-9 px-3 text-sm font-medium text-white bg-[#5e1985] rounded-lg
              hover:bg-[#4a1369] transition-colors no-underline"
          >
            <i className="fa-solid fa-pen-to-square text-xs" />
            일정 등록 신청
          </a>
          <form onSubmit={handleSearch} className="flex items-center gap-1.5">
            <div className="relative">
              <input
                type="text"
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                placeholder="일정 검색"
                className="w-[200px] h-9 pl-8 pr-3 text-sm border border-gray-300 rounded-lg
                  focus:outline-none focus:border-[#5e1985] focus:ring-1 focus:ring-[#5e1985]/30
                  placeholder:text-gray-400"
              />
              <i className="fa-solid fa-magnifying-glass absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-gray-400" />
            </div>
            <button
              type="submit"
              className="h-9 px-3 text-sm font-medium text-white bg-[#5e1985] rounded-lg
                hover:bg-[#4a1369] transition-colors"
            >
              검색
            </button>
          </form>
          </div>
        </div>
      </div>

      {/* Search Results */}
      {searchWord && (
        <div className="mb-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-gray-800 flex items-center gap-1.5">
              <i className="fa-solid fa-magnifying-glass text-[#5e1985] text-xs" />
              "<span className="text-[#5e1985]">{searchWord}</span>" 검색결과
              <span className="font-normal text-gray-400">({searchResults.length}건)</span>
            </h3>
            <button
              onClick={clearSearch}
              className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
            >
              <i className="fa-solid fa-xmark" /> 검색 초기화
            </button>
          </div>
          {searching ? (
            <div className="flex items-center justify-center py-8 text-gray-400 text-sm">
              <i className="fa-solid fa-spinner fa-spin mr-2" />
              검색 중...
            </div>
          ) : searchResults.length === 0 ? (
            <div className="p-6 text-center text-gray-400 text-sm bg-gray-50 rounded-lg border border-dashed border-gray-200">
              검색 결과가 없습니다.
            </div>
          ) : (
            <div className="grid gap-3">
              {searchResults.map(s => (
                <EventCard key={s.id} schedule={s} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Category Tabs */}
      {!searchWord && (
        <>
          <CategoryTabs
            selected={selectedCategory}
            onSelect={setSelectedCategory}
          />

          {/* Main Layout: Sidebar + Calendar */}
          <div className="flex flex-col lg:flex-row gap-5 items-start">
            {/* Sidebar */}
            <Sidebar recent={recent} selectedCategory={selectedCategory} />

            {/* Main Content */}
            <div className="flex-1 min-w-0">
              {loading ? (
                <div className="flex items-center justify-center py-20 text-gray-400">
                  <i className="fa-solid fa-spinner fa-spin mr-2" />
                  일정을 불러오는 중...
                </div>
              ) : (
                <>
                  <Calendar
                    year={year}
                    month={month}
                    schedules={filtered}
                    selectedDate={selectedDate}
                    onSelectDate={setSelectedDate}
                    onPrevMonth={handlePrevMonth}
                    onNextMonth={handleNextMonth}
                  />
                  <DetailPanel
                    selectedDate={selectedDate}
                    schedules={filtered}
                  />
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
