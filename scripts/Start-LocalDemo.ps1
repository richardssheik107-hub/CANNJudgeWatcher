[CmdletBinding()]
param(
    [string]$PythonPath,
    [ValidateRange(1, 65535)][int]$Port = 8088,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'LocalDemo.Common.ps1')
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$dataDirectory = Join-Path $repoRoot 'data'
$databasePath = Join-Path $dataDirectory 'demo.sqlite3'
$recordPath = Join-Path $dataDirectory "local-demo-$Port.process.json"
$url = "http://127.0.0.1:$Port"
$launchArguments = Get-DemoLaunchArguments -Root $repoRoot -Port $Port
$record = $null
$startedHere = $false
$process = $null
$createdProcessTimeTicks = $null
$lockStream = $null

try {
    if ($PythonPath) {
        $pythonExecutable = (Get-Item -LiteralPath $PythonPath -ErrorAction Stop).FullName
    }
    else {
        $candidates = @(
            (Join-Path $repoRoot '.venv\Scripts\python.exe'),
            (Join-Path (Split-Path $repoRoot -Parent) '.validation-venv\Scripts\python.exe')
        )
        $pythonExecutable = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $pythonExecutable) {
            throw 'No installed virtual environment found. Supply -PythonPath C:\path\to\python.exe (Python 3.11+ with requirements.txt installed).'
        }
    }
    if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) { throw 'PythonPath must name an installed Python executable.' }
    New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
    # Prevent simultaneous launches from reseeding or racing to overwrite the PID record.
    $lockStream = [System.IO.File]::Open((Join-Path $dataDirectory 'local-demo.launch.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $checkScript = Join-Path $PSScriptRoot 'check_local_demo.py'
    & $pythonExecutable -X utf8 $checkScript
    if ($LASTEXITCODE -ne 0) { throw 'Runtime check failed; install requirements.txt into the selected environment before starting.' }
    $record = Read-DemoRecord -Path $recordPath -Root $repoRoot -Port $Port
    if ($null -ne $record) {
        $existing = @()
        foreach ($identity in @($record.Processes)) {
            $item = Get-VerifiedTrackedProcess -Identity $identity -LaunchArguments $launchArguments
            if ($null -ne $item) { $existing += $item }
        }
        if ($existing.Count -gt 0) {
            $listeners = Get-DemoListeners -Port $Port
            if ($listeners.Count -eq 1 -and $listeners[0].LocalAddress -eq '127.0.0.1' -and
                @($existing.Id) -contains [int]$listeners[0].OwningProcess) {
                $health = Get-DemoHealth -Port $Port
                if ($health.status -eq 'ok' -and $health.collector_enabled -eq $false) {
                    & $pythonExecutable -X utf8 $checkScript --db $databasePath
                    if ($LASTEXITCODE -ne 0) { throw 'Existing demo data check failed.' }
                    Write-Host "Local demo already running: $url"
                    if (-not $NoBrowser) { Start-Process $url }
                    exit 0
                }
            }
            throw "Tracked demo is still starting or unhealthy. Use Stop-LocalDemo.ps1 -Port $Port, then retry."
        }
    }
    $listeners = Get-DemoListeners -Port $Port
    if ($listeners.Count -gt 0) {
        $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
        throw "Port $Port is occupied by PID(s) $owners. No existing service will be stopped. Choose -Port 8089 or stop that service yourself."
    }
    # Also detect an unavailable port if Windows excludes it from listener enumeration.
    $probe = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
    $probe.Server.ExclusiveAddressUse = $true
    try { $probe.Start() }
    catch { throw "Port $Port cannot be bound: $($_.Exception.Message)" }
    finally { $probe.Stop() }

    Push-Location $repoRoot
    try {
        if (-not (Test-Path -LiteralPath $databasePath)) {
            & $pythonExecutable -X utf8 -m watcher --db $databasePath demo
            if ($LASTEXITCODE -ne 0) { throw 'First-time demo generation failed; existing files were kept for inspection.' }
        }
        & $pythonExecutable -X utf8 $checkScript --db $databasePath
        if ($LASTEXITCODE -ne 0) { throw 'Existing database is not a verified synthetic demo. It was kept without reseeding or replacement.' }
    }
    finally { Pop-Location }

    $runTag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $outputLog = Join-Path $dataDirectory "local-demo-$Port-$runTag.stdout.log"
    $errorLog = Join-Path $dataDirectory "local-demo-$Port-$runTag.stderr.log"
    $oldUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process')
    $oldToken = [Environment]::GetEnvironmentVariable('WATCHER_TOKEN', 'Process')
    # Discard a stale record before spawning, so failure cannot clean up an older
    # record while overlooking the new process created in this invocation.
    $record = $null
    try {
        [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'Process')
        # This localhost-only synthetic run does not inherit a live deployment token.
        [Environment]::SetEnvironmentVariable('WATCHER_TOKEN', '', 'Process')
        $process = Start-Process -FilePath $pythonExecutable -ArgumentList $launchArguments -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $outputLog -RedirectStandardError $errorLog -PassThru
        $startedHere = $true
        $createdProcessTimeTicks = $process.StartTime.ToUniversalTime().Ticks
    }
    finally {
        [Environment]::SetEnvironmentVariable('PYTHONUTF8', $oldUtf8, 'Process')
        [Environment]::SetEnvironmentVariable('WATCHER_TOKEN', $oldToken, 'Process')
    }
    $identity = Get-StartedDemoRootIdentity -Process $process -ExecutablePath $pythonExecutable -LaunchArguments $launchArguments -CreationTicks $createdProcessTimeTicks
    if ($null -eq $identity) { throw "Server exited immediately. See $errorLog" }
    $record = [pscustomobject]@{
        Version = 1; Root = $repoRoot; Port = $Port; Status = 'starting'
        LaunchArguments = $launchArguments; StartedAt = (Get-Date).ToUniversalTime().ToString('o')
        StoppedAt = $null; OutputLog = $outputLog; ErrorLog = $errorLog; Processes = @($identity)
    }
    Save-DemoRecord -Path $recordPath -Record $record
    $ready = $false
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        Update-DemoTrackedProcesses -Record $record
        Save-DemoRecord -Path $recordPath -Record $record
        $listeners = Get-DemoListeners -Port $Port
        if ($listeners.Count -gt 0) {
            if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1') {
                throw "Unexpected listener on port $Port; startup aborted."
            }
            $listenerId = [int]$listeners[0].OwningProcess
            if (-not (Test-DemoDescendant -ProcessId $listenerId -RootProcessId $process.Id)) {
                throw "Port $Port was claimed by another process; it will not be stopped."
            }
            $listenerIdentity = Get-DemoProcessIdentity -ProcessId $listenerId -LaunchArguments $launchArguments
            if (@($record.Processes.Id) -notcontains $listenerId) {
                $record.Processes = @($record.Processes) + @($listenerIdentity)
                Save-DemoRecord -Path $recordPath -Record $record
            }
            try {
                $health = Get-DemoHealth -Port $Port
                if ($health.status -eq 'ok' -and $health.collector_enabled -eq $false) { $ready = $true; break }
            }
            catch { }
        }
        if ($null -eq (Get-DemoProcessIdentity -ProcessId $process.Id -LaunchArguments $launchArguments)) { break }
        Start-Sleep -Milliseconds 350
    }
    if (-not $ready) { throw "Local demo did not become healthy within 20 seconds. See $errorLog" }
    $record.Status = 'running'
    Save-DemoRecord -Path $recordPath -Record $record
    Write-Host "Local demo ready: $url"
    Write-Host "Collector is disabled. PID record: $recordPath"
    Write-Host "Logs: $outputLog / $errorLog"
    if (-not $NoBrowser) { Start-Process $url }
}
catch {
    $failureMessage = $_.Exception.Message
    if ($startedHere) {
        try {
            if ($null -eq $record) {
                # Retry initial identity registration using the exact process object
                # returned by Start-Process; never infer ownership from a port alone.
                $identity = Get-StartedDemoRootIdentity -Process $process -ExecutablePath $pythonExecutable -LaunchArguments $launchArguments -CreationTicks $createdProcessTimeTicks
                if ($null -eq $identity) { throw 'Created launcher already exited before it could be safely registered.' }
                $record = [pscustomobject]@{
                    Version = 1; Root = $repoRoot; Port = $Port; Status = 'starting'
                    LaunchArguments = $launchArguments; StartedAt = (Get-Date).ToUniversalTime().ToString('o')
                    StoppedAt = $null; OutputLog = $outputLog; ErrorLog = $errorLog; Processes = @($identity)
                }
            }
            # A child may exist without a listener (for example while SQLite is
            # locked). Register it before terminating its launcher on failure.
            Update-DemoTrackedProcesses -Record $record
            Save-DemoRecord -Path $recordPath -Record $record
            Stop-DemoTrackedProcesses -Record $record
            $record.Status = 'failed'
            $record.StoppedAt = (Get-Date).ToUniversalTime().ToString('o')
            Save-DemoRecord -Path $recordPath -Record $record
        }
        catch { Write-Warning "Startup cleanup: $($_.Exception.Message)" }
    }
    Write-Error $failureMessage -ErrorAction Continue
    exit 1
}
finally {
    if ($null -ne $lockStream) { $lockStream.Dispose() }
}
