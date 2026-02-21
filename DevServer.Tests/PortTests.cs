using System.Net;
using System.Net.Sockets;
using DevServer;

namespace DevServer.Tests;

[TestFixture]
public class PortTests
{
    [Test]
    public void IsPortAvailable_UnusedPort_ReturnsTrue()
    {
        var port = GetFreePort();
        Assert.That(PortUtils.IsPortAvailable(port), Is.True);
    }

    [Test]
    public void IsPortAvailable_UsedPort_ReturnsFalse()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;

        Assert.That(PortUtils.IsPortAvailable(port), Is.False);
    }

    [Test]
    public void IsPortAvailable_PortBecomesAvailableAfterRelease()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;

        Assert.That(PortUtils.IsPortAvailable(port), Is.False);

        listener.Stop();

        Assert.That(PortUtils.IsPortAvailable(port), Is.True);
    }

    [Test]
    public void WaitForPortAvailable_AlreadyFree_ReturnsImmediately()
    {
        var port = GetFreePort();

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var result = PortUtils.WaitForPortAvailable(port, 5000);
        sw.Stop();

        Assert.That(result, Is.True);
        Assert.That(sw.ElapsedMilliseconds, Is.LessThan(1000),
            "Should return almost immediately for a free port");
    }

    [Test]
    public void WaitForPortAvailable_PortBusy_TimesOut()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var result = PortUtils.WaitForPortAvailable(port, 1000, pollIntervalMs: 100);
        sw.Stop();

        Assert.That(result, Is.False);
        Assert.That(sw.ElapsedMilliseconds, Is.GreaterThanOrEqualTo(900),
            "Should wait close to the full timeout");
    }

    [Test]
    public void WaitForPortAvailable_PortReleasedDuringWait_ReturnsTrue()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;

        // Release the port after 500ms in a background task
        _ = Task.Run(async () =>
        {
            await Task.Delay(500);
            listener.Stop();
        });

        var result = PortUtils.WaitForPortAvailable(port, 5000, pollIntervalMs: 100);

        Assert.That(result, Is.True);
    }

    private static int GetFreePort()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }
}
