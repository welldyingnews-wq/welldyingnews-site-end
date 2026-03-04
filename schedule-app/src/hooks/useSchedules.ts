import { useState, useEffect, useCallback } from 'react'
import type { Schedule } from '../types'

interface ScheduleData {
  schedules: Schedule[]
  upcoming: Schedule[]
  recent: Schedule[]
}

export function useSchedules(year: number, month: number) {
  const [data, setData] = useState<ScheduleData>({ schedules: [], upcoming: [], recent: [] })
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/schedules?year=${year}&month=${month}`)
      if (res.ok) {
        const json = await res.json()
        setData(json)
      }
    } catch (err) {
      console.error('Failed to fetch schedules:', err)
    } finally {
      setLoading(false)
    }
  }, [year, month])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return { ...data, loading }
}
