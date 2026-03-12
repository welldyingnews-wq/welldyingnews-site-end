import type { CategoryKey } from './types'

export const CATEGORIES: { key: CategoryKey; label: string; color: string }[] = [
  { key: '공고',   label: '공고',   color: '#64748B' },
  { key: '교육',   label: '교육',   color: '#3B82F6' },
  { key: '세미나', label: '세미나', color: '#10B981' },
  { key: '토론회', label: '토론회', color: '#F59E0B' },
  { key: '공청회', label: '공청회', color: '#EF4444' },
  { key: '학술대회', label: '학술대회', color: '#8B5CF6' },
  { key: '예술',   label: '예술',   color: '#EC4899' },
  { key: '행사',   label: '행사',   color: '#F97316' },
  { key: '강연',   label: '강연',   color: '#06B6D4' },
  { key: '상담',   label: '상담',   color: '#14B8A6' },
  { key: '모임',   label: '모임',   color: '#A855F7' },
]

export const CATEGORY_COLOR_MAP: Record<string, string> = Object.fromEntries(
  CATEGORIES.map(c => [c.key, c.color])
)

export const DAY_NAMES = ['일', '월', '화', '수', '목', '금', '토']
