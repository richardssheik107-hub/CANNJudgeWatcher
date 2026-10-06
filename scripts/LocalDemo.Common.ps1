# Shared helpers: tracked identities are checked before any process is stopped.
Set-StrictMode -Version Latest

function Get-DemoLaunchArguments {
    param([string]$Root, [int]$Port)
    # These paths are constructed here, not accepted as arbitrary command text.
    $dbPath = Join-Path $Root 'data\demo.sqlite3'
    $configPath = Join-Path $Root 'config\monitor.json'
    if ($Root.Contains('"')) { throw 'Repository path cannot contain a quotation mark.' }
    return '-m watcher --db "' + $dbPath + '" --config "' + $configPath + '" serve --host 127.0.0.1 --port ' + $Port
}

function Get-DemoProcessIdentity {
    param([int]$ProcessId, [string]$LaunchArguments)
    $item = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    if ($null -eq $item) { return $null }
    if ([string]::IsNullOrWhiteSpace($item.CommandLine) -or
        [string]::IsNullOrWhiteSpace($item.ExecutablePath) -or
        -not $item.CommandLine.TrimEnd().EndsWith($LaunchArguments, [StringComparison]::OrdinalIgnoreCase)) {
        throw "PID $ProcessId does not match this local demo command; it will not be stopped."
    }
    return [pscustomobject]@{
        Id = [int]$item.ProcessId
        ParentId = [int]$item.ParentProcessId
        ExecutablePath = [string]$item.ExecutablePath
        CommandLine = [string]$item.CommandLine
        CreationTicks = $item.CreationDate.ToUniversalTime().Ticks.ToString()
    }
}

function Get-VerifiedTrackedProcess {
    param($Identity, [string]$LaunchArguments)
    $current = Get-DemoProcessIdentity -ProcessId ([int]$Identity.Id) -LaunchArguments $LaunchArguments
    if ($null -eq $current) { return $null }
    if ($current.CreationTicks -ne [string]$Identity.CreationTicks -or
        -not [string]::Equals($current.ExecutablePath, [string]$Identity.ExecutablePath, [StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals($current.CommandLine, [string]$Identity.CommandLine, [StringComparison]::OrdinalIgnoreCase)) {
        throw "PID $($Identity.Id) identity changed; it will not be stopped."
    }
    return $current
}

function Get-StartedDemoRootIdentity {
    param($Process, [string]$ExecutablePath, [string]$LaunchArguments, $CreationTicks)
    if ($null -eq $Process) { return $null }
    if ($null -eq $CreationTicks) { $CreationTicks = $Process.StartTime.ToUniversalTime().Ticks }
    $identity = Get-DemoProcessIdentity -ProcessId $Process.Id -LaunchArguments $LaunchArguments
    if ($null -eq $identity) { return $null }
    # Win32_Process timestamps have microsecond precision whereas Process.StartTime
    # can retain 100ns ticks. Permit only that sub-microsecond rounding difference.
    $creationDifference = [long]$identity.CreationTicks - [long]$CreationTicks
    if (-not [string]::Equals($identity.ExecutablePath, $ExecutablePath, [StringComparison]::OrdinalIgnoreCase) -or
        $creationDifference -lt -9 -or $creationDifference -gt 9) {
        throw "Created PID $($Process.Id) no longer matches its executable and creation time; it will not be stopped."
    }
    return $identity
}

function Read-DemoRecord {
    param([string]$Path, [string]$Root, [int]$Port)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $record = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($record.Version -ne 1 -or $record.Port -ne $Port -or
        -not [string]::Equals([string]$record.Root, $Root, [StringComparison]::OrdinalIgnoreCase) -or
        $record.LaunchArguments -ne (Get-DemoLaunchArguments -Root $Root -Port $Port)) {
        throw "Process record does not match this repository and port: $Path"
    }
    return $record
}

function Save-DemoRecord {
    param([string]$Path, $Record)
    $Record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-DemoListeners {
    param([int]$Port)
    return ,@(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Get-DemoHealth {
    param([int]$Port)
    $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$Port/health")
    $request.Proxy = $null
    $request.Timeout = 1200
    $response = $null
    $reader = $null
    try {
        $response = $request.GetResponse()
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        return $reader.ReadToEnd() | ConvertFrom-Json
    }
    finally {
        if ($null -ne $reader) { $reader.Dispose() }
        if ($null -ne $response) { $response.Close() }
    }
}

function Test-DemoDescendant {
    param([int]$ProcessId, [int]$RootProcessId)
    $nextId = $ProcessId
    for ($depth = 0; $depth -lt 8; $depth++) {
        if ($nextId -eq $RootProcessId) { return $true }
        $item = Get-CimInstance Win32_Process -Filter "ProcessId = $nextId" -ErrorAction Stop
        if ($null -eq $item -or $item.ParentProcessId -eq 0) { return $false }
        $nextId = [int]$item.ParentProcessId
    }
    return $false
}

function Update-DemoTrackedProcesses {
    param($Record)
    # Discover children before they listen. In particular, a Windows venv launcher
    # can be waiting for a Python child blocked on SQLite initialization.
    $queue = New-Object 'System.Collections.Generic.Queue[object]'
    foreach ($identity in @($Record.Processes)) {
        $current = Get-VerifiedTrackedProcess -Identity $identity -LaunchArguments $Record.LaunchArguments
        if ($null -ne $current) { $queue.Enqueue($current) }
    }
    $rootCreationTicks = [long]$Record.Processes[0].CreationTicks
    $visited = @{}
    while ($queue.Count -gt 0) {
        $parent = $queue.Dequeue()
        if ($visited.ContainsKey($parent.Id)) { continue }
        $visited[$parent.Id] = $true
        # Recheck the parent's identity just before querying its children: a reused
        # PID must never turn an unrelated process tree into tracked demo processes.
        if ($null -eq (Get-VerifiedTrackedProcess -Identity $parent -LaunchArguments $Record.LaunchArguments)) { continue }
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($parent.Id)" -ErrorAction Stop)
        foreach ($child in $children) {
            if ([string]::IsNullOrWhiteSpace($child.CommandLine) -or
                -not $child.CommandLine.TrimEnd().EndsWith($Record.LaunchArguments, [StringComparison]::OrdinalIgnoreCase)) {
                continue
            }
            $identity = Get-DemoProcessIdentity -ProcessId ([int]$child.ProcessId) -LaunchArguments $Record.LaunchArguments
            if ($null -eq $identity -or $identity.ParentId -ne $parent.Id -or
                [long]$identity.CreationTicks -lt $rootCreationTicks) { continue }
            # Check the parent once more after reading the child identity.
            if ($null -eq (Get-VerifiedTrackedProcess -Identity $parent -LaunchArguments $Record.LaunchArguments)) { continue }
            if (@($Record.Processes.Id) -notcontains $identity.Id) {
                $Record.Processes = @($Record.Processes) + @($identity)
            }
            $queue.Enqueue($identity)
        }
    }
}

function Stop-DemoTrackedProcesses {
    param($Record)
    # Verify all currently existing recorded identities before stopping any of them.
    $verified = @()
    foreach ($identity in @($Record.Processes)) {
        $item = Get-VerifiedTrackedProcess -Identity $identity -LaunchArguments $Record.LaunchArguments
        if ($null -ne $item) { $verified += $item }
    }
    # The listener is recorded after the venv launcher, so stop it first.
    [array]::Reverse($verified)
    foreach ($identity in $verified) {
        $current = Get-VerifiedTrackedProcess -Identity $identity -LaunchArguments $Record.LaunchArguments
        if ($null -ne $current) {
            Stop-Process -Id $current.Id -ErrorAction Stop
            Wait-Process -Id $current.Id -Timeout 10 -ErrorAction SilentlyContinue
            if ($null -ne (Get-CimInstance Win32_Process -Filter "ProcessId = $($current.Id)" -ErrorAction Stop)) {
                throw "Tracked PID $($current.Id) did not exit."
            }
        }
    }
}
