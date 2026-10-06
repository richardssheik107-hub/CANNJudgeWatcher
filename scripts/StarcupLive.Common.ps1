# Fixed public Starcup final profile, sharing the verified process safety helpers.
. (Join-Path $PSScriptRoot 'LocalDemo.Common.ps1')

function Get-StarcupLaunchArguments {
    param([string]$Root, [int]$Port)
    if ($Root.Contains('"')) { throw 'Repository path cannot contain a quotation mark.' }
    $dbPath = Join-Path $Root 'data\starcup-final.sqlite3'
    $configPath = Join-Path $Root 'config\monitor.starcup-final.json'
    return '-m watcher --db "' + $dbPath + '" --config "' + $configPath + '" serve --host 127.0.0.1 --port ' + $Port + ' --poll'
}

function Assert-StarcupRecord {
    param($Record, [string]$Root, [int]$Port)
    if ($Record.Version -ne 1 -or $Record.Port -ne $Port -or
        -not [string]::Equals([string]$Record.Root, $Root, [StringComparison]::OrdinalIgnoreCase) -or
        $Record.LaunchArguments -ne (Get-StarcupLaunchArguments -Root $Root -Port $Port)) {
        throw 'Starcup process record does not match this repository, port and public profile.'
    }
}

function Read-StarcupRecord {
    param([string]$Path, [string]$Root, [int]$Port)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $record = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-StarcupRecord -Record $record -Root $Root -Port $Port
    return $record
}

function Save-StarcupRecord {
    param([string]$Path, $Record)
    Assert-StarcupRecord -Record $Record -Root $Record.Root -Port $Record.Port
    $Record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}
