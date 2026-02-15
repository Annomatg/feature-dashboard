# DevServer - Auto-Reloading Backend Development Server

A C# .NET application that watches Python files and automatically restarts the FastAPI backend server when changes are detected.

## Features

- **File Watching**: Monitors `backend/*.py`, `api/*.py`, and `mcp_server/*.py` for changes
- **Auto-Restart**: Automatically restarts uvicorn when Python files change (2-second delay)
- **Debouncing**: Prevents rapid restarts from multiple file changes (1-second debounce)
- **Single Instance**: Uses mutex to prevent multiple DevServer instances from running
- **Clean Shutdown**: Properly kills the entire uvicorn process tree on Windows

## Usage

### Start DevServer

```bash
# From project root
dotnet run --project DevServer
```

Or use the convenience script:

```bash
# Windows - starts both backend and frontend
start-all.bat
```

### Single Instance Protection

DevServer uses a named mutex to prevent multiple instances from running simultaneously. If you try to start a second instance, you'll see:

```
ERROR: DevServer is already running!
Only one instance of DevServer can run at a time.
```

This prevents:
- Accidental port conflicts (multiple processes trying to bind to port 8000)
- Resource waste from duplicate file watchers
- Confusion from multiple server instances

### Stopping DevServer

Press `Ctrl+C` in the DevServer window to gracefully shutdown.

## How It Works

1. **Watches Python directories** for file changes
2. **Detects changes** to `*.py` files
3. **Stops current uvicorn** process (kills entire process tree)
4. **Waits 2 seconds** for port to be released
5. **Starts new uvicorn** process with the updated code

## Port Information

- Backend server runs on: `http://localhost:8000`
- API documentation: `http://localhost:8000/docs`

## Important Notes

- **DO NOT** manually start uvicorn while DevServer is running
- DevServer manages the backend process automatically
- Only one instance of DevServer can run at a time
- The 2-second restart delay ensures Python releases port 8000 properly
