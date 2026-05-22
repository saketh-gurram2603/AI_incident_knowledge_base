import { useState } from 'react'
import { ChevronDown, ChevronUp, CheckCircle } from 'lucide-react'
import type { ResolutionOption } from '../api/searchApi'

interface Props {
  options: ResolutionOption[]
}

export default function ResolutionPanel({ options }: Props) {
  const [expanded, setExpanded] = useState<number | null>(0)

  if (!options.length) return null

  return (
    <div className="mt-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
        <CheckCircle className="w-4 h-4 text-green-600" />
        Resolution Options ({options.length})
      </h3>
      <div className="space-y-2">
        {options.map((opt, i) => (
          <div key={i} className="border border-gray-200 rounded-lg overflow-hidden">
            <button
              onClick={() => setExpanded(expanded === i ? null : i)}
              className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50
                         hover:bg-gray-100 transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-blue-700 bg-blue-100 px-2 py-0.5 rounded">
                  Fix {i + 1}
                </span>
                <span className="text-xs text-gray-500">
                  Used {opt.occurrence_count}× in past incidents
                </span>
              </div>
              {expanded === i ? (
                <ChevronUp className="w-4 h-4 text-gray-400" />
              ) : (
                <ChevronDown className="w-4 h-4 text-gray-400" />
              )}
            </button>
            {expanded === i && (
              <div className="px-4 py-3 text-sm text-gray-700 bg-white leading-relaxed">
                {opt.resolution_text}
                {opt.source_incident_ids?.length > 0 && (
                  <p className="mt-2 text-xs text-gray-400">
                    Sources: {opt.source_incident_ids.slice(0, 4).join(', ')}
                    {opt.source_incident_ids.length > 4 && ' …'}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
