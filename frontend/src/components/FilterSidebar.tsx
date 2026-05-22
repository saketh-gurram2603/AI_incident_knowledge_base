import type { SearchFilters } from '../api/searchApi'

interface Props {
  filters: SearchFilters
  onChange: (f: SearchFilters) => void
}

const PRIORITIES = ['P1', 'P2', 'P3', 'P4']
const IMPACTS    = ['High', 'Medium', 'Low']
const CATEGORIES = ['Database', 'Storage', 'Network', 'Application',
                    'Performance', 'Hardware', 'Security']

function Select({
  label, value, options, onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="input text-sm"
      >
        <option value="">All</option>
        {options.map(o => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  )
}

export default function FilterSidebar({ filters, onChange }: Props) {
  return (
    <aside className="w-52 flex-shrink-0 space-y-4">
      <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Filters</h2>

      <Select
        label="Priority"
        value={filters.priority ?? ''}
        options={PRIORITIES}
        onChange={v => onChange({ ...filters, priority: v || undefined })}
      />
      <Select
        label="Impact"
        value={filters.impact ?? ''}
        options={IMPACTS}
        onChange={v => onChange({ ...filters, impact: v || undefined })}
      />
      <Select
        label="Category"
        value={filters.category ?? ''}
        options={CATEGORIES}
        onChange={v => onChange({ ...filters, category: v || undefined })}
      />

      <button
        onClick={() => onChange({})}
        className="btn-secondary w-full text-xs"
      >
        Clear filters
      </button>
    </aside>
  )
}
