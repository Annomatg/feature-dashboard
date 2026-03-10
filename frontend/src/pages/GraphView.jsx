import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import LogSidePanel from '../components/LogSidePanel'

cytoscape.use(dagre)

// Node color by agent type
const NODE_COLOR = {
  main: '#22d3ee',
  Explore: '#4ade80',
  'general-purpose': '#a78bfa',
  Plan: '#fb923c',
  'code-review': '#f472b6',
  'deep-dive': '#38bdf8',
  'git-workflow': '#facc15',
  'test-reporter': '#34d399',
  'playwright-tester': '#c084fc',
}

const DEFAULT_COLOR = '#475569'
const MAIN_SIZE = 32
const NODE_SIZE = 22

function getNodeColor(type) {
  return NODE_COLOR[type] || DEFAULT_COLOR
}

function GraphView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const containerRef = useRef(null)
  const cyRef = useRef(null)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const [nodeCount, setNodeCount] = useState(0)
  const [edgeCount, setEdgeCount] = useState(0)
  const [selectedNode, setSelectedNode] = useState(null)

  const handleClosePanel = useCallback(() => {
    setSelectedNode(null)
    // Deselect all nodes in the graph
    if (cyRef.current) {
      cyRef.current.$(':selected').unselect()
    }
  }, [])

  useEffect(() => {
    let destroyed = false

    async function fetchAndRender() {
      try {
        const res = await fetch(`/api/tasks/${id}/graph`)
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(data.detail || `HTTP ${res.status}`)
        }
        const { nodes, edges } = await res.json()

        if (destroyed) return

        const elements = [
          ...nodes.map(n => ({
            data: { id: n.id, label: n.label, type: n.type },
          })),
          ...edges.map(e => ({
            data: { source: e.source, target: e.target },
          })),
        ]

        if (cyRef.current) {
          cyRef.current.destroy()
        }

        cyRef.current = cytoscape({
          container: containerRef.current,
          elements,
          style: [
            {
              selector: 'node',
              style: {
                'background-color': ele => getNodeColor(ele.data('type')),
                label: 'data(label)',
                color: '#cbd5e1',
                'font-size': '10px',
                'font-family': '"JetBrains Mono", monospace',
                'text-valign': 'center',
                'text-halign': 'right',
                'text-margin-x': 10,
                'text-background-color': '#0f172a',
                'text-background-opacity': 0.8,
                'text-background-padding': '3px',
                width: NODE_SIZE,
                height: NODE_SIZE,
                'border-width': 2,
                'border-color': '#1e293b',
              },
            },
            {
              selector: 'node[type = "main"]',
              style: {
                width: MAIN_SIZE,
                height: MAIN_SIZE,
                'border-width': 3,
                'border-color': '#0891b2',
                'font-size': '11px',
                color: '#e2e8f0',
              },
            },
            {
              selector: 'edge',
              style: {
                width: 1.5,
                'line-color': '#334155',
                'target-arrow-color': '#475569',
                'target-arrow-shape': 'triangle',
                'curve-style': 'bezier',
                opacity: 0.8,
              },
            },
            {
              selector: 'node:selected',
              style: {
                'border-color': '#22d3ee',
                'border-width': 3,
              },
            },
          ],
          layout: {
            name: 'dagre',
            rankDir: 'LR',
            nodeSep: 50,
            rankSep: 100,
            padding: 40,
            animate: false,
          },
          wheelSensitivity: 0.3,
          minZoom: 0.2,
          maxZoom: 4,
        })

        // Attach tap handler to open log side panel on node click
        cyRef.current.on('tap', 'node', (evt) => {
          const node = evt.target
          setSelectedNode({
            id: node.data('id'),
            label: node.data('label'),
            type: node.data('type'),
          })
        })

        // Expose cy instance on container for E2E testing
        if (containerRef.current) {
          containerRef.current._cy = cyRef.current
        }

        setNodeCount(nodes.length)
        setEdgeCount(edges.length)
        setStatus('success')
      } catch (err) {
        if (!destroyed) {
          setError(err.message)
          setStatus('error')
        }
      }
    }

    fetchAndRender()

    return () => {
      destroyed = true
      if (cyRef.current) {
        cyRef.current.destroy()
        cyRef.current = null
      }
    }
  }, [id])

  return (
    <div className="h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-4 px-4 py-3 border-b border-gray-800 flex-shrink-0">
        <button
          onClick={() => navigate('/')}
          className="text-gray-400 hover:text-cyan-400 transition-colors text-sm font-mono flex-shrink-0"
        >
          ← Back
        </button>
        <h1 className="text-gray-300 font-mono text-sm truncate">
          Agent Graph — Task #{id}
        </h1>
        {status === 'success' && (
          <span className="ml-auto text-gray-500 font-mono text-xs flex-shrink-0">
            {nodeCount} nodes · {edgeCount} edges
          </span>
        )}
      </div>

      {/* Graph area */}
      <div className="flex-1 relative overflow-hidden">
        {/* Always-rendered Cytoscape container */}
        <div
          ref={containerRef}
          data-testid="graph-container"
          className="w-full h-full"
        />

        {/* Loading overlay */}
        {status === 'loading' && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950">
            <span className="text-gray-400 font-mono text-sm">Loading graph…</span>
          </div>
        )}

        {/* Error overlay */}
        {status === 'error' && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950">
            <div className="text-center max-w-sm px-4">
              <p className="text-red-400 font-mono text-sm mb-2">Failed to load graph</p>
              <p className="text-gray-500 font-mono text-xs">{error}</p>
            </div>
          </div>
        )}

        {/* Log side panel — shown when a node is selected */}
        {selectedNode && (
          <LogSidePanel
            taskId={id}
            node={selectedNode}
            onClose={handleClosePanel}
          />
        )}
      </div>

      {/* Legend (shown on success) */}
      {status === 'success' && (
        <div className="flex items-center gap-3 px-4 py-2 border-t border-gray-800 flex-shrink-0 flex-wrap">
          {Object.entries(NODE_COLOR).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1.5">
              <div
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="text-gray-500 font-mono text-xs">{type}</span>
            </div>
          ))}
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: DEFAULT_COLOR }} />
            <span className="text-gray-500 font-mono text-xs">other</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default GraphView
