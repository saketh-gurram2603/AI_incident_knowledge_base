import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Search, Zap, Clock } from 'lucide-react'
import { searchIncidents, type SearchFilters, type SearchResponse } from '../api/searchApi'
import IncidentCard from '../components/IncidentCard'
import FilterSidebar from '../components/FilterSidebar'
import ResolutionPanel from '../components/ResolutionPanel'

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<SearchFilters>({})

  const mutation = useMutation({
    mutationFn: () => searchIncidents({ query, filters }),
  })

  const data: SearchResponse | undefined = mutation.data

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (query.trim().length < 3) return
    mutation.mutate()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Incident Search</h1>
        <p className="text-sm text-gray-500 mt-1">
          Hybrid BM25 + vector search with cross-encoder reranking
        </p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            className="input pl-9"
            placeholder="Describe the incident — e.g. database connection pool exhausted..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
        </div>
        <button
          type="submit"
          className="btn-primary px-5"
          disabled={query.trim().length < 3 || mutation.isPending}
        >
          {mutation.isPending ? 'Searching…' : 'Search'}
        </button>
      </form>

      {/* Error */}
      {mutation.isError && (
        <div className="card border-red-200 bg-red-50 text-red-700 text-sm">
          {(mutation.error as Error).message}
        </div>
      )}

      {/* Results */}
      {data && (
        <div className="flex gap-6">
          {/* Sidebar */}
          <FilterSidebar filters={filters} onChange={setFilters} />

          {/* Main content */}
          <div className="flex-1 space-y-4">
            {/* Stats bar */}
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <Zap className="w-3.5 h-3.5 text-blue-500" />
                {data.total} result{data.total !== 1 ? 's' : ''} ·
                method: <span className="font-medium text-gray-700">{data.retrieval_method}</span>
                {data.cached && <span className="ml-1 badge bg-green-100 text-green-700">cached</span>}
              </span>
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {data.latency_ms.toFixed(0)} ms · k={data.adaptive_k_used}
              </span>
            </div>

            {/* Resolution panel */}
            {data.resolution_options.length > 0 && (
              <div className="card border-blue-100 bg-blue-50">
                <h2 className="text-sm font-semibold text-blue-800 mb-1">
                  Synthesised Resolution Options
                </h2>
                <ResolutionPanel options={data.resolution_options} />
              </div>
            )}

            {/* Incident cards */}
            {data.results.length === 0 ? (
              <div className="text-center py-12 text-gray-400 text-sm">
                No matching incidents found. Try a different query.
              </div>
            ) : (
              <div className="space-y-3">
                {data.results.map((item, i) => (
                  <IncidentCard key={item.incident_id} item={item} rank={i + 1} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!data && !mutation.isPending && (
        <div className="text-center py-20 text-gray-400">
          <Search className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">Enter an incident description to search the knowledge base</p>
        </div>
      )}
    </div>
  )
}
