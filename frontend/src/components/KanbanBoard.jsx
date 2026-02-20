import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import KanbanLane from './KanbanLane'
import Toast from './Toast'
import DetailPanel from './DetailPanel'
import Header from './Header'
import InfoBar from './InfoBar'

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

const DONE_PAGE_SIZE = 20

async function fetchFeatures() {
  const response = await fetch('/api/features?passes=false')
  if (!response.ok) {
    throw new Error('Failed to fetch features')
  }
  return response.json()
}

async function fetchDoneFeatures(limit, offset) {
  const response = await fetch(`/api/features?passes=true&limit=${limit}&offset=${offset}`)
  if (!response.ok) {
    throw new Error('Failed to fetch done features')
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

async function fetchDatabases() {
  const response = await fetch('/api/databases')
  if (!response.ok) throw new Error('Failed to fetch databases')
  return response.json()
}

async function reorderFeature(featureId, targetId, insertBefore) {
  const response = await fetch(`/api/features/${featureId}/reorder`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_id: targetId, insert_before: insertBefore })
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to reorder feature')
  }
  return response.json()
}

// Determine the next lane state when moving a feature
function getLaneState(lane) {
  if (lane === 'inProgress') return { in_progress: true, passes: false }
  if (lane === 'done') return { passes: true, in_progress: false }
  return { passes: false, in_progress: false } // todo
}

function getLaneLabel(lane) {
  if (lane === 'inProgress') return 'In Progress'
  if (lane === 'done') return 'Done'
  return 'Todo'
}

function KanbanBoard() {
  const [selectedFeatureId, setSelectedFeatureId] = useState(null)
  const [addingToLane, setAddingToLane] = useState(null)
  const [toast, setToast] = useState(null)
  const [panelFeature, setPanelFeature] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [doneOffset, setDoneOffset] = useState(0)
  const [doneFeatures, setDoneFeatures] = useState([])
  const [doneTotalCount, setDoneTotalCount] = useState(0)
  const [infoDismissed, setInfoDismissed] = useState(false)

  const queryClient = useQueryClient()
  const dragState = useRef(null)

  const isInteracting = addingToLane !== null || isDragging

  // Fetch non-done features (todo + in-progress)
  const { data: features = [], isLoading, error } = useQuery({
    queryKey: ['features'],
    queryFn: fetchFeatures,
    // Pause polling while user is creating a feature or dragging a card
    refetchInterval: isInteracting ? false : 5000,
  })

  // Fetch databases to determine if a non-default DB is active
  const { data: databases = [] } = useQuery({
    queryKey: ['databases'],
    queryFn: fetchDatabases,
    staleTime: 30000,
  })

  // Fetch done features separately with pagination
  const { data: doneData, isLoading: isDoneLoading } = useQuery({
    queryKey: ['features', 'done', doneOffset],
    queryFn: () => fetchDoneFeatures(DONE_PAGE_SIZE, doneOffset),
    refetchInterval: isInteracting ? false : 5000,
  })

  // Sync done features data - append when loading more pages, replace on first page
  useEffect(() => {
    if (!doneData) return
    setDoneTotalCount(doneData.total)
    if (doneOffset === 0) {
      setDoneFeatures(doneData.features)
    } else {
      setDoneFeatures(prev => {
        // Avoid duplicates when refetch returns same data
        const existingIds = new Set(prev.map(f => f.id))
        const newFeatures = doneData.features.filter(f => !existingIds.has(f.id))
        return [...prev, ...newFeatures]
      })
    }
  }, [doneData, doneOffset])

  const invalidateDoneFeatures = () => {
    // Reset pagination offset and invalidate cache so query refetches fresh data.
    // Do NOT clear doneFeatures eagerly — the useEffect will replace them once
    // the fresh query result arrives, preventing a flash of empty content.
    setDoneOffset(0)
    queryClient.invalidateQueries(['features', 'done'])
  }

  const createFeatureMutation = useMutation({
    mutationFn: createFeature,
    onSuccess: () => {
      queryClient.invalidateQueries(['features'])
      invalidateDoneFeatures()
      setAddingToLane(null)
      setToast({ type: 'success', message: 'Feature created successfully' })
    },
    onError: (error) => {
      setToast({ type: 'error', message: error.message })
    }
  })

  const moveToLaneMutation = useMutation({
    mutationFn: ({ featureId, stateData }) => updateFeatureState(featureId, stateData),
    onSuccess: (_, { toLane }) => {
      queryClient.invalidateQueries(['features'])
      invalidateDoneFeatures()
      setToast({ type: 'success', message: `Moved to ${getLaneLabel(toLane)}` })
    },
    onError: (error) => {
      setToast({ type: 'error', message: error.message })
    }
  })

  const reorderMutation = useMutation({
    mutationFn: ({ featureId, targetId, insertBefore }) => reorderFeature(featureId, targetId, insertBefore),
    onSuccess: () => {
      queryClient.invalidateQueries(['features'])
    },
    onError: (error) => {
      setToast({ type: 'error', message: error.message })
    }
  })

  // Derive activeDbPath here (before early returns) so the useEffect hook order is stable
  const activeDbPath = databases.find(db => db.is_active)?.path

  // Reset dismiss state whenever the active database changes
  useEffect(() => {
    setInfoDismissed(false)
  }, [activeDbPath])

  if (isLoading) {
    return (
      <div className="h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-text-secondary font-mono text-sm">Loading features...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-screen bg-background flex items-center justify-center">
        <div className="text-center max-w-md">
          <div className="text-6xl mb-4">⚠️</div>
          <h2 className="text-2xl font-bold text-error mb-2">Error Loading Features</h2>
          <p className="text-text-secondary">{error.message}</p>
        </div>
      </div>
    )
  }

  // Filter features by lane (done features come from separate paginated query)
  const todoFeatures = features.filter(LANE_CONFIG.todo.filter)
  const inProgressFeatures = features.filter(LANE_CONFIG.inProgress.filter)

  const handleShowMoreDone = () => {
    setDoneOffset(prev => prev + DONE_PAGE_SIZE)
  }

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

  const handleMoveToLane = (feature, toLane) => {
    moveToLaneMutation.mutate({
      featureId: feature.id,
      stateData: getLaneState(toLane),
      toLane
    })
  }

  const handleReorder = (feature, targetId, insertBefore) => {
    reorderMutation.mutate({ featureId: feature.id, targetId, insertBefore })
  }

  const handleCardClick = (feature) => {
    setSelectedFeatureId(feature.id)
    setPanelFeature(feature)
  }

  const handlePanelClose = () => {
    setPanelFeature(null)
    setSelectedFeatureId(null)
  }

  const handlePanelUpdate = (updatedFeature) => {
    queryClient.invalidateQueries(['features'])
    invalidateDoneFeatures()
    setPanelFeature(updatedFeature)
  }

  const handlePanelDelete = () => {
    queryClient.invalidateQueries(['features'])
    invalidateDoneFeatures()
  }

  const handleDragStart = () => {
    setIsDragging(true)
  }

  const handleDragEnd = () => {
    setIsDragging(false)
  }

  const totalFeatures = features.length + doneTotalCount
  const inProgressCount = inProgressFeatures.length

  // Show info bar when a non-default database is active
  const activeDb = databases.find(db => db.is_active)
  const defaultDb = databases[0]
  const showInfoBar = !infoDismissed && databases.length > 1 && activeDb && activeDbPath !== defaultDb?.path
  const infoBarMessage = showInfoBar ? `Active database: ${activeDb.name}` : null

  return (
    <div className="h-screen bg-background flex flex-col">
      <Header
        totalFeatures={totalFeatures}
        inProgressCount={inProgressCount}
        doneCount={doneTotalCount}
      />

      {showInfoBar && (
        <InfoBar
          message={infoBarMessage}
          type="info"
          onDismiss={() => setInfoDismissed(true)}
        />
      )}

      <div className="flex-1 overflow-hidden px-6 pb-6 pt-6">
        {/* Kanban Board - 3 Column Layout */}
        <div className="max-w-[1800px] mx-auto grid grid-cols-3 grid-rows-1 gap-6 h-full">
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
            onMoveToLane={handleMoveToLane}
            onReorder={handleReorder}
            dragState={dragState}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
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
            onMoveToLane={handleMoveToLane}
            onReorder={handleReorder}
            dragState={dragState}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          />

          <KanbanLane
            title={LANE_CONFIG.done.title}
            count={doneTotalCount}
            features={doneFeatures}
            accentColor={LANE_CONFIG.done.accentColor}
            onAddClick={() => handleAddFeature('done')}
            selectedFeatureId={selectedFeatureId}
            onCardClick={handleCardClick}
            isAddingFeature={addingToLane === 'done'}
            onSaveFeature={handleSaveFeature}
            onCancelAdd={handleCancelAdd}
            lane="done"
            onMoveToLane={handleMoveToLane}
            onReorder={handleReorder}
            dragState={dragState}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            isDoneLane={true}
            hasMore={doneFeatures.length < doneTotalCount}
            onShowMore={handleShowMoreDone}
            isLoadingMore={isDoneLoading && doneOffset > 0}
          />
        </div>

      </div>

      {/* Toast notifications */}
      {toast && (
        <div className="fixed bottom-4 right-4 z-50">
          <Toast
            type={toast.type}
            message={toast.message}
            onClose={() => setToast(null)}
          />
        </div>
      )}

      {/* Detail Panel */}
      {panelFeature && (
        <DetailPanel
          feature={panelFeature}
          onClose={handlePanelClose}
          onUpdate={handlePanelUpdate}
          onDelete={handlePanelDelete}
        />
      )}
    </div>
  )
}

export default KanbanBoard
