import { useState, useRef, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Database, Loader2 } from 'lucide-react'

async function fetchDatabases() {
  const response = await fetch('/api/databases')
  if (!response.ok) throw new Error('Failed to fetch databases')
  return response.json()
}

async function selectDatabase(path) {
  const response = await fetch('/api/databases/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path })
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to switch database')
  }
  return response.json()
}

function DatabaseSelector() {
  const [open, setOpen] = useState(false)
  const [switching, setSwitching] = useState(false)
  const dropdownRef = useRef(null)
  const queryClient = useQueryClient()

  const { data: databases = [] } = useQuery({
    queryKey: ['databases'],
    queryFn: fetchDatabases,
    staleTime: 30000,
  })

  const active = databases.find(db => db.is_active)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  async function handleSelect(db) {
    if (db.is_active || switching) return
    setOpen(false)
    setSwitching(true)
    try {
      await selectDatabase(db.path)
      // Invalidate all feature-related caches so they reload from new DB
      await queryClient.invalidateQueries()
    } catch (err) {
      console.error('Failed to switch database:', err)
    } finally {
      setSwitching(false)
    }
  }

  const availableDbs = databases.filter(db => db.exists)

  // Don't render if only one database
  if (databases.length <= 1 && !switching) {
    return null
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen(o => !o)}
        disabled={switching}
        className="flex items-center gap-2 px-3 py-1.5 rounded border border-border bg-surface text-text-secondary hover:text-text-primary hover:border-primary/50 transition-colors font-mono text-sm disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {switching ? (
          <Loader2 size={14} className="animate-spin text-primary" />
        ) : (
          <Database size={14} />
        )}
        <span className="max-w-[180px] truncate">
          {switching ? 'Switching...' : (active?.name ?? 'Select Database')}
        </span>
        <ChevronDown
          size={12}
          className={`transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 min-w-[220px] bg-surface border border-border rounded shadow-lg z-50">
          {availableDbs.map(db => (
            <button
              key={db.path}
              onClick={() => handleSelect(db)}
              className={`w-full text-left flex items-center gap-2 px-3 py-2 font-mono text-sm transition-colors
                ${db.is_active
                  ? 'text-primary bg-primary/10 cursor-default'
                  : 'text-text-secondary hover:text-text-primary hover:bg-white/5 cursor-pointer'
                }`}
            >
              <Database size={13} className={db.is_active ? 'text-primary' : 'text-text-secondary'} />
              <span className="truncate">{db.name}</span>
              {db.is_active && (
                <span className="ml-auto text-xs text-primary font-mono">active</span>
              )}
            </button>
          ))}
          {availableDbs.length === 0 && (
            <p className="px-3 py-2 text-text-secondary text-xs font-mono">No databases found</p>
          )}
        </div>
      )}
    </div>
  )
}

export default DatabaseSelector
