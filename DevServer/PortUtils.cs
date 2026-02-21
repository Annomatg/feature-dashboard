using System.Diagnostics;
using System.Net;
using System.Net.Sockets;

namespace DevServer;

public static class PortUtils
{
    public const int DefaultPollIntervalMs = 250;

    public static bool IsPortAvailable(int port)
    {
        try
        {
            using var listener = new TcpListener(IPAddress.Loopback, port);
            listener.Start();
            listener.Stop();
            return true;
        }
        catch (SocketException)
        {
            return false;
        }
    }

    public static bool WaitForPortAvailable(int port, int timeoutMs, int pollIntervalMs = DefaultPollIntervalMs)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < timeoutMs)
        {
            if (IsPortAvailable(port))
                return true;
            Thread.Sleep(pollIntervalMs);
        }
        return false;
    }

    public static void KillProcessTree(int pid, int timeoutMs = 5000)
    {
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
        killProcess.StandardOutput.ReadToEnd();
        var stderr = killProcess.StandardError.ReadToEnd();
        killProcess.WaitForExit(timeoutMs);

        if (killProcess.ExitCode != 0 && !string.IsNullOrWhiteSpace(stderr))
        {
            Console.WriteLine($"taskkill stderr: {stderr.Trim()}");
        }
    }

    public static void KillProcessOnPort(int port)
    {
        try
        {
            var netstat = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = $"/c netstat -ano | findstr :{port} | findstr LISTENING",
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    CreateNoWindow = true
                }
            };

            netstat.Start();
            var output = netstat.StandardOutput.ReadToEnd();
            netstat.WaitForExit(5000);

            foreach (var line in output.Split('\n', StringSplitOptions.RemoveEmptyEntries))
            {
                var parts = line.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length > 0 && int.TryParse(parts[^1], out int pid) && pid > 0)
                {
                    Console.WriteLine($"Killing process {pid} on port {port}");
                    KillProcessTree(pid);
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Warning: Could not kill process on port {port}: {ex.Message}");
        }
    }
}
