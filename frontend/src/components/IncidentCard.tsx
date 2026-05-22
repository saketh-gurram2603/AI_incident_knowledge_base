import { useState } from 'react'
import { ChevronDown, ChevronUp, Tag } from 'lucide-react'
import type { SearchResultItem } from '../api/searchApi'

interface Props {
  item: SearchResultItem
  rank: number
}

const PRIORITY_COLORS: Record<string, string> = {
  P1: 'bg-red-100 text-red-700',
  P2: 'bg-orange-100 text-orange-700',
  P3: 'bg-yellow-100 text-yellow-700',
  P4: 'bg-gray-100 text-gray-600',
}

export default function IncidentCard({ item, rank }: Props) {
  const [expanded, setExpanded] = useState(false)
  const priorityStyle = PRIORITY_COLORS[item.priority ?? ''] ?? 'bg-gray-100 text-gray-600'
  const scorePercent = Math.round((item.similarity_score ?? 0) * 100)

  return (
    <div className="card hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-3">
        {/* Rank bubble */}
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-600 text-white text-xs
                        font-bold flex items-center justify-center mt-0.5">
          {rank}
        </div>

        <div className="flex-1 min-w-0">
          {/* Title + badges */}
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-gray-900 truncate">
              {item.title || item.incident_id}
            </h3>
            {item.priority && (
              <span className={`badge text-xs font-medium ${priorityStyle}`}>
                {item.priority}
              </span>
            )}
            {item.category && (
              <span className="badge bg-blue-50 text-blue-700 text-xs">
                <Tag className="w-3 h-3 mr-1" />{item.category}
              </span>
            )}
          </div>

          {/* Score bar */}
          <div className="flex items-center gap-2 mb-2">
            <div className="w-20 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full"
                style={{ width: `${scorePercent}%` }}
              />
            </div>
            <span className="text-xs text-gray-500">Match {scorePercent}%</span>
          </div>

          {/* Description preview */}
          <p className="text-sm text-gray-600 line-clamp-2">
            {item.description || 'No description available.'}
          </p>

          {/* Expand / collapse */}
          {item.resolution_notes && (
            <>
              <button
                onClick={() => setExpanded(!expanded)}
                className="mt-2 flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800
                           font-medium transition-colors"
              >
                {expanded ? (
                  <><ChevronUp className="w-3.5 h-3.5" /> Hide resolution</>
                ) : (
                  <><ChevronDown className="w-3.5 h-3.5" /> Show resolution</>
                )}
              </button>
              {expanded && (
                <div className="mt-2 p-3 bg-green-50 border border-green-100 rounded-lg
                                text-sm text-gray-700 leading-relaxed">
                  <span className="text-xs font-semibold text-green-700 block mb-1">
                    Resolution
                  </span>
                  {item.resolution_notes}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
