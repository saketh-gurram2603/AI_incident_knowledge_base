import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { BarChart2, CheckCircle, XCircle, Play, RefreshCw } from 'lucide-react'
import {
  getLatestMetrics,
  runEvaluation,
  type MetricScore,
} from '../api/evaluationApi'
import MetricChart from '../components/MetricChart'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'

const LABEL_MAP: Record<string, string> = {
  ndcg_at_k:                'NDCG@10',
  map_at_k:                 'MAP@10',
  recall_at_k:              'Recall@10',
  precision_at_k:           'P@10',
  avg_faithfulness:         'Faithfulness',
  avg_answer_relevancy:     'Relevancy',
  avg_contextual_precision: 'Ctx Precision',
}

function MetricRow({ m }: { m: MetricScore }) {
  const pct = Math.round(m.score * 100)
  const threshPct = Math.round(m.threshold * 100)
  return (
    <div className="flex items-center gap-3 py-2 border-b border-gray-100 last:border-0">
      <div className="w-36 text-xs text-gray-600 font-medium flex-shrink-0">
        {LABEL_MAP[m.name] ?? m.name}
      </div>
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden relative">
        <div
          className={`h-full rounded-full ${m.passed ? 'bg-blue-500' : 'bg-red-400'}`}
          style={{ width: `${pct}%` }}
        />
        {/* threshold marker */}
        <div
          className="absolute top-0 h-full w-px bg-amber-400"
          style={{ left: `${threshPct}%` }}
        />
      </div>
      <span className="w-10 text-right text-xs tabular-nums font-semibold text-gray-700">
        {pct}%
      </span>
      <div className="w-5">
        {m.passed
          ? <CheckCircle className="w-4 h-4 text-green-500" />
          : <XCircle className="w-4 h-4 text-red-400" />
        }
      </div>
    </div>
  )
}

export default function AnalyticsPage() {
  const [runLlmJudge, setRunLlmJudge] = useState(false)

  const { data: latest, refetch, isFetching } = useQuery({
    queryKey: ['metrics'],
    queryFn: getLatestMetrics,
  })

  const evalMutation = useMutation({
    mutationFn: () =>
      runEvaluation({ run_ir_metrics: true, run_llm_judge: runLlmJudge }),
    onSuccess: () => refetch(),
  })

  const metrics = latest?.metrics ?? []
  const hasData = metrics.length > 0

  // Bar chart data
  const barData = metrics.map(m => ({
    name: LABEL_MAP[m.name] ?? m.name,
    score: Math.round(m.score * 100),
    threshold: Math.round(m.threshold * 100),
    passed: m.passed,
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-sm text-gray-500 mt-1">
            IR metrics (NDCG, MAP, Recall, Precision) + LLM-as-Judge evaluation
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={runLlmJudge}
              onChange={e => setRunLlmJudge(e.target.checked)}
              className="rounded border-gray-300 text-blue-600"
            />
            Include LLM Judge
          </label>

          <button
            onClick={() => evalMutation.mutate()}
            disabled={evalMutation.isPending}
            className="btn-primary flex items-center gap-1.5 text-sm"
          >
            {evalMutation.isPending ? (
              <><RefreshCw className="w-4 h-4 animate-spin" /> Running…</>
            ) : (
              <><Play className="w-4 h-4" /> Run Evaluation</>
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {evalMutation.isError && (
        <div className="card border-red-200 bg-red-50 text-red-700 text-sm">
          {(evalMutation.error as Error).message}
        </div>
      )}

      {/* No data */}
      {!hasData && !evalMutation.isPending && (
        <div className="text-center py-20 text-gray-400">
          <BarChart2 className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No evaluation data yet. Click "Run Evaluation" to start.</p>
        </div>
      )}

      {hasData && (
        <>
          {/* Run metadata */}
          <div className="flex items-center gap-4 text-xs text-gray-500">
            {latest?.run_id && (
              <span className="font-mono text-gray-700">{latest.run_id}</span>
            )}
            {latest?.timestamp && (
              <span>{new Date(latest.timestamp).toLocaleString()}</span>
            )}
            <span className={`badge text-xs font-semibold ${
              latest?.overall_passed
                ? 'bg-green-100 text-green-700'
                : 'bg-red-100 text-red-700'
            }`}>
              {latest?.overall_passed ? 'All Passed' : 'Some Failed'}
            </span>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="ml-auto flex items-center gap-1 text-blue-600 hover:text-blue-800"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Bar chart */}
            <div className="card">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">Scores vs Thresholds</h2>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={barData} margin={{ top: 4, right: 8, left: -20, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10, fill: '#6b7280' }}
                    angle={-35}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 10, fill: '#9ca3af' }}
                    tickFormatter={v => `${v}%`}
                  />
                  <Tooltip formatter={(v: number) => `${v}%`} />
                  <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                    {barData.map((entry, i) => (
                      <Cell key={i} fill={entry.passed ? '#3b82f6' : '#f87171'} />
                    ))}
                  </Bar>
                  <ReferenceLine y={50} stroke="#f59e0b" strokeDasharray="4 2"
                                 label={{ value: 'Threshold ~', position: 'right', fontSize: 9 }} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Radar chart */}
            <div className="card">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">Radar Overview</h2>
              <MetricChart metrics={metrics} />
              <p className="text-xs text-gray-400 text-center mt-1">
                Blue = score · Amber dashed = threshold
              </p>
            </div>
          </div>

          {/* Metric rows */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Metric Detail</h2>
            <div>
              {metrics.map(m => <MetricRow key={m.name} m={m} />)}
            </div>
            <p className="text-xs text-gray-400 mt-2">
              Amber line = passing threshold · Blue = IR metrics · Bars = score %
            </p>
          </div>
        </>
      )}
    </div>
  )
}
