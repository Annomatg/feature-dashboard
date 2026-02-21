using System.Diagnostics;

namespace DevServer;

class Program
{
    private static readonly string ProjectDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
    private static readonly string BackendDir = Path.Combine(ProjectDir, "backend");
    private static readonly string ApiDir = Path.Combine(ProjectDir, "api");
    private static readonly string McpDir = Path.Combine(ProjectDir, "mcp_server");
    private static readonly string PythonExe = Path.Combine(ProjectDir, "venv", "Scripts", "python.exe");

    private static Process? _serverProcess;
    private static readonly object _lock = new();
    private static CancellationTokenSource? _restartCts;
    private static Mutex? _instanceMutex;

    internal const int ServerPort = 8000;
    internal const int DebounceMs = 1000;
    internal const int PortWaitTimeoutMs = 10000;
    internal const int ProcessExitWaitMs = 3000;

    static async Task Main(string[] args)
    {
        // Prevent multiple instances using a named mutex
        const string mutexName = "FeatureDashboardDevServer_SingleInstance";
        _instanceMutex = new Mutex(true, mutexName, out bool createdNew);

        if (!createdNew)
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("=== Feature Dashboard Dev Server ===");
            Console.WriteLine();
            Console.WriteLine("ERROR: DevServer is already running!");
            Console.WriteLine("Only one instance of DevServer can run at a time.");
            Console.WriteLine();
            Console.WriteLine("If you believe this is an error, close all DevServer windows");
            Console.WriteLine("and try again. Press any key to exit...");
            Console.ResetColor();
            Console.ReadKey();
            return;
        }

        Console.WriteLine("=== Feature Dashboard Dev Server ===");
        Console.WriteLine($"Project:  {ProjectDir}");
        Console.WriteLine($"Backend:  {BackendDir}");
        Console.WriteLine($"API:      {ApiDir}");
        Console.WriteLine($"MCP:      {McpDir}");
        Console.WriteLine($"Python:   {PythonExe}");
        Console.WriteLine();

        if (!Directory.Exists(BackendDir))
        {
            Console.WriteLine($"ERROR: Backend directory not found: {BackendDir}");
            return;
        }

        if (!File.Exists(PythonExe))
        {
            Console.WriteLine($"ERROR: Python not found: {PythonExe}");
            return;
        }

        // Setup file watchers for all Python directories
        var watchers = new List<FileSystemWatcher>();

        foreach (var dir in new[] { BackendDir, ApiDir, McpDir })
        {
            if (Directory.Exists(dir))
            {
                var watcher = new FileSystemWatcher(dir);
                watcher.Filter = "*.py";
                watcher.NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.FileName;
                watcher.Changed += OnFileChanged;
                watcher.Created += OnFileChanged;
                watcher.EnableRaisingEvents = true;
                watchers.Add(watcher);
                Console.WriteLine($"Watching: {Path.GetFileName(dir)}/*.py");
            }
        }

        Console.WriteLine("Press Ctrl+C to stop");
        Console.WriteLine();

        // Handle Ctrl+C
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            StopServer();
            foreach (var watcher in watchers)
                watcher.Dispose();
            _instanceMutex?.ReleaseMutex();
            _instanceMutex?.Dispose();
            Environment.Exit(0);
        };

        // Start server initially
        StartServer();

        // Keep running
        await Task.Delay(-1);
    }

    private static void OnFileChanged(object sender, FileSystemEventArgs e)
    {
        lock (_lock)
        {
            // Cancel any pending restart (debounce)
            _restartCts?.Cancel();
            _restartCts?.Dispose();
            _restartCts = new CancellationTokenSource();
            var token = _restartCts.Token;

            // Schedule restart after debounce period
            Task.Run(async () =>
            {
                try
                {
                    await Task.Delay(DebounceMs, token);
                }
                catch (TaskCanceledException)
                {
                    return; // Another change came in, this restart was superseded
                }

                Console.WriteLine($"\n[{DateTime.Now:HH:mm:ss}] Change detected: {e.Name}");
                RestartServer();
            });
        }
    }

    private static void StartServer()
    {
        lock (_lock)
        {
            Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] Starting server...");

            var startInfo = new ProcessStartInfo
            {
                FileName = PythonExe,
                Arguments = "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000",
                WorkingDirectory = ProjectDir,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            _serverProcess = new Process { StartInfo = startInfo };

            _serverProcess.OutputDataReceived += (_, args) =>
            {
                if (!string.IsNullOrEmpty(args.Data))
                    Console.WriteLine(args.Data);
            };

            _serverProcess.ErrorDataReceived += (_, args) =>
            {
                if (!string.IsNullOrEmpty(args.Data))
                    Console.WriteLine(args.Data);
            };

            _serverProcess.Start();
            _serverProcess.BeginOutputReadLine();
            _serverProcess.BeginErrorReadLine();

            Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] Server started (PID: {_serverProcess.Id})");
        }
    }

    private static void StopServer()
    {
        lock (_lock)
        {
            if (_serverProcess == null || _serverProcess.HasExited)
            {
                _serverProcess = null;
                return;
            }

            var pid = _serverProcess.Id;
            Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] Stopping server (PID: {pid})...");

            try
            {
                // Kill the process tree (uvicorn spawns child processes)
                PortUtils.KillProcessTree(pid);

                // Wait for process to actually exit
                if (!_serverProcess.HasExited)
                {
                    var exited = _serverProcess.WaitForExit(ProcessExitWaitMs);
                    if (!exited)
                    {
                        Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] WARNING: Process {pid} did not exit within {ProcessExitWaitMs}ms, attempting direct kill...");
                        try
                        {
                            _serverProcess.Kill(entireProcessTree: true);
                            _serverProcess.WaitForExit(ProcessExitWaitMs);
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] WARNING: Direct kill failed: {ex.Message}");
                        }
                    }
                }

                Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] Server stopped (PID: {pid})");
            }
            catch (InvalidOperationException)
            {
                Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] Server already stopped (PID: {pid})");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] Warning stopping server: {ex.Message}");
            }

            _serverProcess = null;
        }
    }

    private static void RestartServer()
    {
        StopServer();

        // Wait for port to be available instead of a fixed sleep
        if (!PortUtils.WaitForPortAvailable(ServerPort, PortWaitTimeoutMs))
        {
            Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] WARNING: Port {ServerPort} still in use after {PortWaitTimeoutMs}ms timeout");
            Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] Attempting to kill any process using port {ServerPort}...");
            PortUtils.KillProcessOnPort(ServerPort);

            if (!PortUtils.WaitForPortAvailable(ServerPort, PortWaitTimeoutMs))
            {
                Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] ERROR: Port {ServerPort} is still in use. Cannot restart server.");
                return;
            }
        }

        StartServer();
    }
}
