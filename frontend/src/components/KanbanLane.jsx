import { Plus } from 'lucide-react'
import KanbanCard from './KanbanCard'
import NewFeatureCard from './NewFeatureCard'

function KanbanLane({
  title,
  count,
  features,
  accentColor,
  onAddClick,
  selectedFeatureId,
  onCardClick,
  isAddingFeature,
  onSaveFeature,
  onCancelAdd,
  lane
}) {
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
        {/* New Feature Card */}
        {isAddingFeature && (
          <NewFeatureCard
            lane={lane}
            onSave={onSaveFeature}
            onCancel={onCancelAdd}
            accentColor={accentColor}
          />
        )}

        {/* Existing Features */}
        {features.length === 0 && !isAddingFeature ? (
          <div className="text-center py-12 px-4">
            <div className="text-4xl mb-3 opacity-20">○</div>
            <p className="text-text-secondary text-sm font-mono">
              No features yet
            </p>
          </div>
        ) : (
          features.map((feature, index) => (
            <KanbanCard
              key={feature.id}
              feature={feature}
              accentColor={accentColor}
              index={index}
              isSelected={selectedFeatureId === feature.id}
              onClick={onCardClick}
            />
          ))
        )}
      </div>
    </div>
  )
}

export default KanbanLane
