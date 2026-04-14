param(
    [switch]$Restart
)

$ErrorActionPreference = "SilentlyContinue"

$ports = @(18789, 5173)
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conn) {
        $pids = $conn | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique
        foreach ($pid in $pids) {
            Write-Host "Killing process $pid on port $port..." -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
}

Start-Sleep -Seconds 1

Write-Host ""
Write-Host "Starting backend (port 18789)..." -ForegroundColor Cyan
Start-Process -FilePath "pwsh" -ArgumentList "-NoExit", "-Command", "cd D:\workspace\code\tigerclaw; uv run tigerclaw gateway start" -WindowTitle "TigerClaw Backend"

Start-Sleep -Seconds 2

Write-Host "Starting frontend (port 5173)..." -ForegroundColor Cyan
Start-Process -FilePath "pwsh" -ArgumentList "-NoExit", "-Command", "cd D:\workspace\code\tigerclaw\ui; npm run dev" -WindowTitle "TigerClaw Frontend"

Start-Sleep -Seconds 3

$backendOk = (Get-NetTCPConnection -LocalPort 18789 -State Listen -ErrorAction SilentlyContinue) -ne $null
$frontendOk = (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) -ne $null

Write-Host ""
if ($backendOk) {
    Write-Host "Backend  http://127.0.0.1:18789  OK" -ForegroundColor Green
} else {
    Write-Host "Backend  http://127.0.0.1:18789  FAILED" -ForegroundColor Red
}
if ($frontendOk) {
    Write-Host "Frontend http://localhost:5173     OK" -ForegroundColor Green
} else {
    Write-Host "Frontend http://localhost:5173     FAILED" -ForegroundColor Red
}

if ($frontendOk) {
    Start-Process "http://localhost:5173"
}
