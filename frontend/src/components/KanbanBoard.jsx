import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import KanbanLane from './KanbanLane'
import Toast from './Toast'

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

async function createFeature(featureData) {
  const response = await fetch('/api/features', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(featureData)
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to create feature')
  }
  return response.json()
}

async function updateFeatureState(featureId, stateData) {
  const response = await fetch(`/api/features/${featureId}/state`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(stateData)
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to update feature state')
  }
  return response.json()
}

async function updateFeaturePriority(featureId, priority) {
  const response = await fetch(`/api/features/${featureId}/priority`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ priority })
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to update feature priority')
  }
  return response.json()
}

function KanbanBoard() {
  const [selectedFeatureId, setSelectedFeatureId] = useState(null)
  const [addingToLane, setAddingToLane] = useState(null)
  const [toast, setToast] = useState(null)

  const queryClient = useQueryClient()

  const { data: features = [], isLoading, error } = useQuery({
    queryKey: ['features'],
    queryFn: fetchFeatures,
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
  })

  const createFeatureMutation = useMutation({
    mutationFn: createFeature,
    onSuccess: () => {
      queryClient.invalidateQueries(['features'])
      setAddingToLane(null)
      setToast({ type: 'success', message: 'Feature created successfully' })
    },
    onError: (error) => {
      setToast({ type: 'error', message: error.message })
    }
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
    setAddingToLane(lane)
  }

  const handleSaveFeature = async (featureData) => {
    const { lane, addToTop, ...apiData } = featureData

    try {
      // Create the feature first (will get max priority + 1)
      const newFeature = await createFeatureMutation.mutateAsync(apiData)

      // If addToTop is true, move the feature to priority 1
      if (addToTop) {
        await updateFeaturePriority(newFeature.id, 1)
      }

      // Set the appropriate lane state
      const stateUpdate = {}
      if (lane === 'inProgress') {
        stateUpdate.in_progress = true
      } else if (lane === 'done') {
        stateUpdate.passes = true
      }

      if (Object.keys(stateUpdate).length > 0) {
        await updateFeatureState(newFeature.id, stateUpdate)
      }

      // Refresh the feature list
      queryClient.invalidateQueries(['features'])
    } catch (error) {
      console.error('Error creating feature:', error)
      throw error
    }
  }

  const handleCancelAdd = () => {
    setAddingToLane(null)
  }

  const handleCardClick = (feature) => {
    setSelectedFeatureId(feature.id)
    // TODO: Open detail panel
    console.log('Selected feature:', feature)
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
            selectedFeatureId={selectedFeatureId}
            onCardClick={handleCardClick}
            isAddingFeature={addingToLane === 'todo'}
            onSaveFeature={handleSaveFeature}
            onCancelAdd={handleCancelAdd}
            lane="todo"
          />

          <KanbanLane
            title={LANE_CONFIG.inProgress.title}
            count={inProgressFeatures.length}
            features={inProgressFeatures}
            accentColor={LANE_CONFIG.inProgress.accentColor}
            onAddClick={() => handleAddFeature('inProgress')}
            selectedFeatureId={selectedFeatureId}
            onCardClick={handleCardClick}
            isAddingFeature={addingToLane === 'inProgress'}
            onSaveFeature={handleSaveFeature}
            onCancelAdd={handleCancelAdd}
            lane="inProgress"
          />

          <KanbanLane
            title={LANE_CONFIG.done.title}
            count={doneFeatures.length}
            features={doneFeatures}
            accentColor={LANE_CONFIG.done.accentColor}
            onAddClick={() => handleAddFeature('done')}
            selectedFeatureId={selectedFeatureId}
            onCardClick={handleCardClick}
            isAddingFeature={addingToLane === 'done'}
            onSaveFeature={handleSaveFeature}
            onCancelAdd={handleCancelAdd}
            lane="done"
          />
        </div>

        {/* Toast notifications */}
        {toast && (
          <Toast
            type={toast.type}
            message={toast.message}
            onClose={() => setToast(null)}
          />
        )}
      </div>
    </div>
  )
}

export default KanbanBoard
