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

Write-Host "All services stopped." -ForegroundColor Green
