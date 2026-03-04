import { CATEGORY_COLOR_MAP } from '../constants'

interface Props {
  category: string
  onClick?: () => void
  size?: 'sm' | 'md'
}

export default function EventBadge({ category, onClick, size = 'sm' }: Props) {
  const color = CATEGORY_COLOR_MAP[category] || '#6B7280'
  const isSmall = size === 'sm'

  return (
    <span
      onClick={onClick}
      className={`inline-block rounded-full font-medium text-white leading-none whitespace-nowrap
        ${isSmall ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs'}
        ${onClick ? 'cursor-pointer hover:opacity-80' : ''}`}
      style={{ backgroundColor: color }}
    >
      {category || '미분류'}
    </span>
  )
}
