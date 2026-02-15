import { Plus } from 'lucide-react'

function KanbanLane({ title, count, features, accentColor, onAddClick }) {
  return (
    <div className="flex flex-col h-full min-w-0 animate-slide-in">
      {/* Lane Header */}
      <div className="flex-shrink-0 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div
              className="w-1 h-8 rounded-full"
              style={{ backgroundColor: accentColor }}
            />
            <h2 className="text-xl font-bold font-mono uppercase tracking-wider text-text-primary">
              {title}
            </h2>
            <div
              className="px-2.5 py-1 rounded font-mono text-sm font-semibold"
              style={{
                backgroundColor: `${accentColor}15`,
                color: accentColor,
                border: `1px solid ${accentColor}40`
              }}
            >
              {count}
            </div>
          </div>

          <button
            onClick={onAddClick}
            className="p-2 rounded transition-all duration-200 hover:bg-surface-light group"
            style={{
              border: '1px solid #3d3d3d'
            }}
            aria-label={`Add feature to ${title}`}
          >
            <Plus
              size={18}
              className="text-text-secondary group-hover:text-text-primary transition-colors"
            />
          </button>
        </div>

        {/* Subtle divider */}
        <div
          className="h-px"
          style={{
            background: `linear-gradient(90deg, ${accentColor}60 0%, transparent 100%)`
          }}
        />
      </div>

      {/* Scrollable Feature List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-3 pr-2">
        {features.length === 0 ? (
          <div className="text-center py-12 px-4">
            <div className="text-4xl mb-3 opacity-20">○</div>
            <p className="text-text-secondary text-sm font-mono">
              No features yet
            </p>
          </div>
        ) : (
          features.map((feature, index) => (
            <FeatureCard
              key={feature.id}
              feature={feature}
              accentColor={accentColor}
              index={index}
            />
          ))
        )}
      </div>
    </div>
  )
}

function FeatureCard({ feature, accentColor, index }) {
  return (
    <div
      className="bg-surface border border-surface-light rounded-lg p-4 hover:border-opacity-60 transition-all duration-200 cursor-pointer group"
      style={{
        borderLeftWidth: '3px',
        borderLeftColor: accentColor,
        animationDelay: `${index * 50}ms`
      }}
    >
      {/* Priority & Category */}
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-xs text-text-secondary">
          #{feature.priority.toString().padStart(3, '0')}
        </span>
        <span
          className="px-2 py-0.5 rounded text-xs font-mono"
          style={{
            backgroundColor: `${accentColor}10`,
            color: accentColor
          }}
        >
          {feature.category}
        </span>
      </div>

      {/* Feature Name */}
      <h3 className="text-text-primary font-semibold mb-2 line-clamp-2 group-hover:text-white transition-colors">
        {feature.name}
      </h3>

      {/* Description */}
      <p className="text-text-secondary text-sm line-clamp-2 mb-3">
        {feature.description}
      </p>

      {/* Steps count */}
      {feature.steps && feature.steps.length > 0 && (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-px bg-surface-light" />
          <span className="text-xs font-mono text-text-secondary">
            {feature.steps.length} {feature.steps.length === 1 ? 'step' : 'steps'}
          </span>
        </div>
      )}
    </div>
  )
}

export default KanbanLane
