interface Props {
  level: 'L1' | 'L2' | 'L3'
  confidence: number
}

const LEVEL_STYLES: Record<string, string> = {
  L1: 'bg-green-100 text-green-800 border-green-200',
  L2: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  L3: 'bg-red-100 text-red-800 border-red-200',
}

const LEVEL_LABELS: Record<string, string> = {
  L1: 'Auto-Resolved',
  L2: 'Web-Augmented',
  L3: 'Escalated',
}

export default function ConfidenceBadge({ level, confidence }: Props) {
  const style = LEVEL_STYLES[level] ?? LEVEL_STYLES.L3
  const label = LEVEL_LABELS[level] ?? level

  return (
    <div className="flex items-center gap-2">
      <span className={`badge border text-xs font-semibold ${style}`}>
        {level} · {label}
      </span>
      <div className="flex items-center gap-1.5">
        <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              confidence >= 0.8
                ? 'bg-green-500'
                : confidence >= 0.55
                ? 'bg-yellow-500'
                : 'bg-red-400'
            }`}
            style={{ width: `${Math.round(confidence * 100)}%` }}
          />
        </div>
        <span className="text-xs text-gray-500 tabular-nums">
          {Math.round(confidence * 100)}%
        </span>
      </div>
    </div>
  )
}
