[CmdletBinding()]
param([ValidateRange(1, 65535)][int]$Port = 8088)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'LocalDemo.Common.ps1')
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$recordPath = Join-Path $repoRoot "data\local-demo-$Port.process.json"
$lockStream = $null
try {
    if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) {
        Write-Host "No local demo PID record for port $Port; no process was stopped."
        exit 0
    }
    $lockStream = [System.IO.File]::Open((Join-Path $repoRoot 'data\local-demo.launch.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $record = Read-DemoRecord -Path $recordPath -Root $repoRoot -Port $Port
    Stop-DemoTrackedProcesses -Record $record
    $record.Status = 'stopped'
    $record.StoppedAt = (Get-Date).ToUniversalTime().ToString('o')
    Save-DemoRecord -Path $recordPath -Record $record
    Write-Host "Tracked local demo stopped for port $Port. Database, PID record and logs were kept."
}
catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
}
finally {
    if ($null -ne $lockStream) { $lockStream.Dispose() }
}
