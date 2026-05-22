import {
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
  ResponsiveContainer, Tooltip,
} from 'recharts'
import type { MetricScore } from '../api/evaluationApi'

interface Props {
  metrics: MetricScore[]
}

const LABEL_MAP: Record<string, string> = {
  ndcg_at_k:               'NDCG@10',
  map_at_k:                'MAP@10',
  recall_at_k:             'Recall@10',
  precision_at_k:          'P@10',
  avg_faithfulness:        'Faithfulness',
  avg_answer_relevancy:    'Relevancy',
  avg_contextual_precision:'Ctx Precision',
}

export default function MetricChart({ metrics }: Props) {
  if (!metrics.length) return null

  const data = metrics.map(m => ({
    metric: LABEL_MAP[m.name] ?? m.name,
    score: Math.round(m.score * 100),
    threshold: Math.round(m.threshold * 100),
  }))

  return (
    <ResponsiveContainer width="100%" height={280}>
      <RadarChart data={data}>
        <PolarGrid stroke="#e5e7eb" />
        <PolarAngleAxis
          dataKey="metric"
          tick={{ fontSize: 11, fill: '#6b7280' }}
        />
        <Radar
          name="Score"
          dataKey="score"
          stroke="#3b82f6"
          fill="#3b82f6"
          fillOpacity={0.25}
          strokeWidth={2}
        />
        <Radar
          name="Threshold"
          dataKey="threshold"
          stroke="#f59e0b"
          fill="#f59e0b"
          fillOpacity={0.10}
          strokeDasharray="4 2"
          strokeWidth={1.5}
        />
        <Tooltip
          formatter={(val: number, name: string) => [`${val}%`, name]}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
        />
      </RadarChart>
    </ResponsiveContainer>
  )
}
