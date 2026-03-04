import { CATEGORIES } from '../constants'

interface Props {
  selected: string | null
  onSelect: (category: string | null) => void
}

export default function CategoryTabs({ selected, onSelect }: Props) {
  return (
    <div className="flex flex-wrap gap-2 mb-4">
      <button
        onClick={() => onSelect(null)}
        className={`px-3 py-1.5 text-sm rounded-full border transition-colors
          ${selected === null
            ? 'bg-[#5e1985] text-white border-[#5e1985]'
            : 'bg-white text-gray-600 border-gray-300 hover:border-[#5e1985] hover:text-[#5e1985]'}`}
      >
        전체일정
      </button>
      {CATEGORIES.map(cat => (
        <button
          key={cat.key}
          onClick={() => onSelect(cat.key)}
          className={`px-3 py-1.5 text-sm rounded-full border transition-colors
            ${selected === cat.key
              ? 'text-white'
              : 'bg-white text-gray-600 border-gray-300 hover:text-gray-900'}`}
          style={selected === cat.key
            ? { backgroundColor: cat.color, borderColor: cat.color }
            : undefined}
        >
          {cat.label}
        </button>
      ))}
    </div>
  )
}
