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
    private static DateTime _lastRestart = DateTime.MinValue;
    private static readonly TimeSpan DebounceTime = TimeSpan.FromSeconds(1);
    private static Mutex? _instanceMutex;

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
            // Debounce rapid changes
            if (DateTime.Now - _lastRestart < DebounceTime)
                return;

            _lastRestart = DateTime.Now;
        }

        Console.WriteLine($"\n[{DateTime.Now:HH:mm:ss}] Change detected: {e.Name}");
        RestartServer();
    }

    private static void StartServer()
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

    private static void StopServer()
    {
        if (_serverProcess == null || _serverProcess.HasExited)
            return;

        Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] Stopping server (PID: {_serverProcess.Id})...");

        try
        {
            // Kill the process tree (uvicorn spawns child processes)
            KillProcessTree(_serverProcess.Id);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Warning: {ex.Message}");
        }

        _serverProcess = null;
    }

    private static void RestartServer()
    {
        StopServer();
        Thread.Sleep(2000); // Pause to ensure port is released (Python can be slow)
        StartServer();
    }

    private static void KillProcessTree(int pid)
    {
        // Use taskkill to kill the entire process tree on Windows
        var killProcess = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = "taskkill",
                Arguments = $"/F /T /PID {pid}",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            }
        };

        killProcess.Start();
        killProcess.WaitForExit(5000);
    }
}
