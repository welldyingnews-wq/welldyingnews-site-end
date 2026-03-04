export interface Schedule {
  id: number
  title: string
  description: string
  content: string        // 본문 HTML (CKEditor)
  event_date: string     // ISO datetime string
  end_date: string | null
  location: string
  category: string
  link_url: string
  image_url: string      // 대표 이미지 URL
  is_active: boolean
}

export type CategoryKey = '교육' | '세미나' | '토론회' | '공청회' | '학술대회' | '예술' | '행사' | '강연' | '공고'
