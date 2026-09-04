# localhost.run tunnel keepalive: auto-reconnect + periodic self-ping to avoid inactivity timeout
# Usage: powershell -ExecutionPolicy Bypass -File tunnel-keepalive.ps1 -Port 8081
param(
    [Parameter(Mandatory = $true)][int]$Port,
    [string]$HealthPath = "/health",
    [int]$PingSeconds = 120
)

$root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$logFile = Join-Path $root ".tunnel-$Port.log"
$urlFile = Join-Path $root ".tunnel-$Port.url"

while ($true) {
    Remove-Item $logFile -Force -ErrorAction SilentlyContinue

    $p = Start-Process -FilePath "ssh.exe" -PassThru -NoNewWindow -RedirectStandardOutput $logFile -ArgumentList @(
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=NUL",
        "-o", "ServerAliveInterval=30",
        "-o", "ExitOnForwardFailure=yes",
        "-R", "80:127.0.0.1:$Port",
        "nokey@localhost.run"
    )

    # wait for the assigned public hostname to show up in the log
    $url = $null
    for ($i = 0; $i -lt 30 -and -not $url; $i++) {
        Start-Sleep -Seconds 2
        if (Test-Path $logFile) {
            $m = Select-String -Path $logFile -Pattern "https://[a-z0-9-]+\.lhr\.life" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value }
        }
    }

    if (-not $url) {
        Write-Host "[$(Get-Date -Format HH:mm:ss)] port $Port : no hostname, retrying"
        if (-not $p.HasExited) { $p | Stop-Process -Force }
        Start-Sleep -Seconds 5
        continue
    }

    Set-Content -Path $urlFile -Value $url -Encoding ascii
    Write-Host "[$(Get-Date -Format HH:mm:ss)] port $Port -> $url"

    # keep traffic flowing while the tunnel is alive
    while (-not $p.HasExited) {
        Start-Sleep -Seconds $PingSeconds
        try { Invoke-WebRequest -Uri "$url$HealthPath" -UseBasicParsing -TimeoutSec 20 | Out-Null } catch { }
    }

    Write-Host "[$(Get-Date -Format HH:mm:ss)] port $Port : tunnel dropped, reconnecting"
    Start-Sleep -Seconds 3
}
