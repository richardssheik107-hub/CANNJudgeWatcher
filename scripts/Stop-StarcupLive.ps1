[CmdletBinding()]
param([ValidateRange(1, 65535)][int]$Port = 8088)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'StarcupLive.Common.ps1')
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$recordPath = Join-Path $repoRoot "data\starcup-live-$Port.process.json"
$lockStream = $null
try {
    if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) {
        Write-Host "No Starcup live PID record for port $Port; no process was stopped."
        exit 0
    }
    $lockStream = [System.IO.File]::Open((Join-Path $repoRoot 'data\starcup-live.launch.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $record = Read-StarcupRecord -Path $recordPath -Root $repoRoot -Port $Port
    Stop-DemoTrackedProcesses -Record $record
    $record.Status = 'stopped'
    $record.StoppedAt = (Get-Date).ToUniversalTime().ToString('o')
    Save-StarcupRecord -Path $recordPath -Record $record
    Write-Host "Tracked Starcup live stopped for port $Port. Database, PID record and logs were kept."
}
catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
}
finally {
    if ($null -ne $lockStream) { $lockStream.Dispose() }
}
