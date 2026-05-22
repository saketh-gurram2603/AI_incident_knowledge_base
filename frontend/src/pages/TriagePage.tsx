import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { GitBranch, AlertTriangle, Clock, Ticket } from 'lucide-react'
import { runTriage, getEscalations, type TriageResult } from '../api/triageApi'
import ConfidenceBadge from '../components/ConfidenceBadge'

const LEVEL_ORDER = ['L1', 'L2', 'L3']

function StepIndicator({ level, active, done }: { level: string; active: boolean; done: boolean }) {
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border
      ${done ? 'bg-green-50 border-green-200 text-green-700'
        : active ? 'bg-blue-50 border-blue-200 text-blue-700'
        : 'bg-gray-50 border-gray-200 text-gray-400'}`}>
      <span className={`w-2 h-2 rounded-full ${done ? 'bg-green-500' : active ? 'bg-blue-500 animate-pulse' : 'bg-gray-300'}`} />
      {level}
    </div>
  )
}

export default function TriagePage() {
  const [description, setDescription] = useState('')
  const [impact, setImpact]   = useState<'' | 'High' | 'Medium' | 'Low'>('')
  const [urgency, setUrgency] = useState<'' | 'High' | 'Medium' | 'Low'>('')
  const [showEscalations, setShowEscalations] = useState(false)

  const triage = useMutation({
    mutationFn: () =>
      runTriage({
        description,
        impact:  impact  || undefined,
        urgency: urgency || undefined,
      }),
  })

  const escalations = useQuery({
    queryKey: ['escalations'],
    queryFn: () => getEscalations(),
    enabled: showEscalations,
  })

  const result: TriageResult | undefined = triage.data

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (description.trim().length < 10) return
    triage.mutate()
  }

  const finalLevel = result?.escalation_level ?? 'L1'
  const finalLevelIndex = LEVEL_ORDER.indexOf(finalLevel)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Triage</h1>
          <p className="text-sm text-gray-500 mt-1">
            L1 → L2 → L3 intelligent escalation pipeline
          </p>
        </div>
        <button
          onClick={() => setShowEscalations(!showEscalations)}
          className="btn-secondary flex items-center gap-1.5 text-sm"
        >
          <Ticket className="w-4 h-4" />
          Escalations
        </button>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="card space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Incident Description <span className="text-red-500">*</span>
          </label>
          <textarea
            className="input min-h-24 resize-none"
            placeholder="Describe the incident in detail — the more specific, the better the triage..."
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={4}
          />
          <p className="mt-1 text-xs text-gray-400">Minimum 10 characters</p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Impact</label>
            <select className="input" value={impact} onChange={e => setImpact(e.target.value as any)}>
              <option value="">Not specified</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Urgency</label>
            <select className="input" value={urgency} onChange={e => setUrgency(e.target.value as any)}>
              <option value="">Not specified</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>
          </div>
        </div>

        <button
          type="submit"
          className="btn-primary w-full"
          disabled={description.trim().length < 10 || triage.isPending}
        >
          {triage.isPending ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Analysing…
            </span>
          ) : (
            'Run Triage'
          )}
        </button>
      </form>

      {/* Error */}
      {triage.isError && (
        <div className="card border-red-200 bg-red-50 text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {(triage.error as Error).message}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-4">
          {/* Pipeline progress */}
          <div className="card">
            <div className="flex items-center gap-3 mb-4">
              <GitBranch className="w-4 h-4 text-gray-500" />
              <span className="text-sm font-medium text-gray-700">Triage Pipeline</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {LEVEL_ORDER.map((lvl, i) => (
                <StepIndicator
                  key={lvl}
                  level={lvl}
                  active={i === finalLevelIndex}
                  done={i < finalLevelIndex}
                />
              ))}
            </div>
          </div>

          {/* Main result card */}
          <div className="card space-y-4">
            {/* Header row */}
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="space-y-1.5">
                <ConfidenceBadge level={result.escalation_level} confidence={result.confidence} />
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  {result.priority && (
                    <span className="font-medium text-gray-700">
                      Priority: {result.priority}
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" />
                    {result.latency_ms.toFixed(0)} ms
                  </span>
                  <span>Model: {result.model_used}</span>
                  {result.fallback_used && (
                    <span className="badge bg-orange-100 text-orange-700">fallback</span>
                  )}
                </div>
              </div>

              {result.escalation_ticket_id && (
                <div className="badge bg-red-100 text-red-700 text-xs border border-red-200">
                  <Ticket className="w-3 h-3 mr-1" />
                  {result.escalation_ticket_id}
                </div>
              )}
            </div>

            {/* Final answer */}
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Final Answer
              </h3>
              <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
                {result.final_answer}
              </div>
            </div>

            {/* L1 summary */}
            {result.l1_summary && result.escalation_level !== 'L1' && (
              <details className="text-sm">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-700 text-xs font-medium">
                  L1 KB Summary
                </summary>
                <div className="mt-2 p-3 bg-blue-50 rounded-lg text-gray-700 leading-relaxed">
                  {result.l1_summary}
                </div>
              </details>
            )}

            {/* L2 synthesis */}
            {result.l2_synthesis && result.escalation_level === 'L3' && (
              <details className="text-sm">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-700 text-xs font-medium">
                  L2 Web-Augmented Synthesis
                </summary>
                <div className="mt-2 p-3 bg-yellow-50 rounded-lg text-gray-700 leading-relaxed">
                  {result.l2_synthesis}
                </div>
              </details>
            )}

            {/* Escalation reason */}
            {result.escalation_reason && (
              <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50
                              border border-amber-200 rounded-lg px-3 py-2">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                {result.escalation_reason}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Escalations panel */}
      {showEscalations && (
        <div className="card space-y-3">
          <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <Ticket className="w-4 h-4" />
            L3 Escalation Tickets
          </h2>
          {escalations.isPending && (
            <p className="text-sm text-gray-400">Loading…</p>
          )}
          {escalations.data?.tickets.length === 0 && (
            <p className="text-sm text-gray-400">No escalation tickets yet.</p>
          )}
          {escalations.data?.tickets.map(t => (
            <div key={t.ticket_id} className="border border-gray-200 rounded-lg p-3 text-sm space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-mono font-semibold text-xs text-blue-700">{t.ticket_id}</span>
                <span className={`badge text-xs ${t.status === 'OPEN' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>
                  {t.status}
                </span>
              </div>
              <p className="text-gray-700 line-clamp-2">{t.description}</p>
              <p className="text-gray-400 text-xs">{new Date(t.created_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
