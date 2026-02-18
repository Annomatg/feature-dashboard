import { Info, X } from 'lucide-react'

const TYPE_STYLES = {
  info: {
    bg: 'rgba(59,130,246,0.08)',
    border: 'rgba(59,130,246,0.25)',
    text: '#93c5fd',
    iconColor: '#60a5fa',
  },
  warning: {
    bg: 'rgba(245,158,11,0.08)',
    border: 'rgba(245,158,11,0.25)',
    text: '#fcd34d',
    iconColor: '#f59e0b',
  },
}

function InfoBar({ message, type = 'info', onDismiss }) {
  const s = TYPE_STYLES[type] || TYPE_STYLES.info

  return (
    <div
      data-testid="info-bar"
      className="relative z-30 flex-shrink-0 flex items-center gap-3 px-6 py-2 border-b"
      style={{
        backgroundColor: s.bg,
        borderColor: s.border,
      }}
    >
      <Info size={14} style={{ color: s.iconColor, flexShrink: 0 }} />
      <p
        className="flex-1 text-sm font-mono"
        style={{ color: s.text }}
      >
        {message}
      </p>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          className="transition-opacity hover:opacity-60"
          style={{ color: s.iconColor }}
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}

export default InfoBar
