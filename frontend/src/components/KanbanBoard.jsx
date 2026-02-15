import { useQuery } from '@tanstack/react-query'
import KanbanLane from './KanbanLane'

const LANE_CONFIG = {
  todo: {
    title: 'TODO',
    accentColor: '#f59e0b', // warning/amber
    filter: (feature) => !feature.passes && !feature.in_progress
  },
  inProgress: {
    title: 'IN PROGRESS',
    accentColor: '#3b82f6', // primary/blue
    filter: (feature) => feature.in_progress
  },
  done: {
    title: 'DONE',
    accentColor: '#22c55e', // success/green
    filter: (feature) => feature.passes
  }
}

async function fetchFeatures() {
  const response = await fetch('/api/features')
  if (!response.ok) {
    throw new Error('Failed to fetch features')
  }
  return response.json()
}

function KanbanBoard() {
  const { data: features = [], isLoading, error } = useQuery({
    queryKey: ['features'],
    queryFn: fetchFeatures,
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
  })

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-text-secondary font-mono text-sm">Loading features...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center max-w-md">
          <div className="text-6xl mb-4">⚠️</div>
          <h2 className="text-2xl font-bold text-error mb-2">Error Loading Features</h2>
          <p className="text-text-secondary">{error.message}</p>
        </div>
      </div>
    )
  }

  // Filter features by lane
  const todoFeatures = features.filter(LANE_CONFIG.todo.filter)
  const inProgressFeatures = features.filter(LANE_CONFIG.inProgress.filter)
  const doneFeatures = features.filter(LANE_CONFIG.done.filter)

  const handleAddFeature = (lane) => {
    // TODO: Implement add feature modal
    console.log(`Add feature to ${lane}`)
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-[1800px] mx-auto">
        {/* Header */}
        <header className="mb-8">
          <div className="flex items-center gap-4 mb-2">
            <div className="w-1.5 h-12 bg-primary rounded-full" />
            <div>
              <h1 className="text-4xl font-bold font-mono text-text-primary tracking-tight">
                FEATURE DASHBOARD
              </h1>
              <p className="text-text-secondary font-mono text-sm mt-1">
                {features.length} total features · {doneFeatures.length} completed
              </p>
            </div>
          </div>
        </header>

        {/* Kanban Board - 3 Column Layout */}
        <div className="grid grid-cols-3 gap-6 h-[calc(100vh-180px)]">
          <KanbanLane
            title={LANE_CONFIG.todo.title}
            count={todoFeatures.length}
            features={todoFeatures}
            accentColor={LANE_CONFIG.todo.accentColor}
            onAddClick={() => handleAddFeature('todo')}
          />

          <KanbanLane
            title={LANE_CONFIG.inProgress.title}
            count={inProgressFeatures.length}
            features={inProgressFeatures}
            accentColor={LANE_CONFIG.inProgress.accentColor}
            onAddClick={() => handleAddFeature('inProgress')}
          />

          <KanbanLane
            title={LANE_CONFIG.done.title}
            count={doneFeatures.length}
            features={doneFeatures}
            accentColor={LANE_CONFIG.done.accentColor}
            onAddClick={() => handleAddFeature('done')}
          />
        </div>
      </div>
    </div>
  )
}

export default KanbanBoard
