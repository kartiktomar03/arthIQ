# Run from a local Windows console. psql owns the hidden password prompt.
[CmdletBinding()]
param([string]$ReportPath, [string]$CsvDirectory = (Join-Path $env:USERPROFILE "Downloads/archive"))

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Normalize-OlistCopy.ps1')

function Get-ImportInputs {
    $tables = @(
        'customers', 'orders', 'order_items', 'order_payments', 'order_reviews',
        'products', 'sellers', 'geolocation', 'product_category_name_translation'
    )
    foreach ($name in 'run_in_pgadmin.sql', 'run_in_psql.sql') {
        $path = Join-Path $PSScriptRoot $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Missing import script: $path"
        }
    }

    # Check the actual client-side COPY paths before prompting or opening a connection.
    $driver = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'run_in_psql.sql')
    $copies = [regex]::Matches($driver, "(?im)^\\copy\s+pg_temp\.src_(\w+)\s+[^\r\n]*?\sFROM\s+'([^']+)'")
    if ($copies.Count -ne $tables.Count) { throw 'Expected nine client-side COPY statements.' }
    foreach ($table in $tables) {
        $matchesForTable = @($copies | Where-Object { $_.Groups[1].Value -eq $table })
        if ($matchesForTable.Count -ne 1) { throw "Expected exactly one COPY for $table." }
        $file = if ($table -eq 'product_category_name_translation') { "$table.csv" } else { "olist_${table}_dataset.csv" }
        $expected = Join-Path (Resolve-Path -LiteralPath $CsvDirectory).Path $file
        $actual = [IO.Path]::GetFullPath($matchesForTable[0].Groups[2].Value)
        if ($actual -ne $expected) { throw "Unexpected COPY source for ${table}: $actual" }
        if (-not (Test-Path -LiteralPath $actual -PathType Leaf)) { throw "Missing CSV: $actual" }
    }
    return $tables
}

function Invoke-OlistPsql([string]$StageDirectory) {
    $exe = Join-Path $env:ProgramFiles 'PostgreSQL\19\bin\psql.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        $exe = (Get-Command psql.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    }
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $exe
    $start.WorkingDirectory = $StageDirectory
    $start.UseShellExecute = $false
    # Leave stdin and stderr attached to the console for psql's non-echoing prompt and errors.
    $start.RedirectStandardOutput = $true
    $start.Arguments = '-X -W --host=127.0.0.1 --port=5432 --username=postgres --dbname=arthiq_olist --set=ON_ERROR_STOP=1 --quiet --no-align --tuples-only --pset=pager=off --file=run_in_psql.sql'
    # Isolate this child from service files, host-address overrides and inherited passwords.
    foreach ($key in @($start.EnvironmentVariables.Keys)) {
        if ($key -like 'PG*') { $start.EnvironmentVariables.Remove($key) }
    }
    $start.EnvironmentVariables['PGCONNECT_TIMEOUT'] = '10'
    $process = [Diagnostics.Process]::Start($start)
    try {
        $output = $process.StandardOutput.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "psql exited with code $($process.ExitCode). Import unverified; see PostgreSQL's error above."
        }
        return $output
    } finally {
        if (-not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
        $process.Dispose()
    }
}

function Show-Verification($json, $tables) {
    $report = $json | ConvertFrom-Json
    if ($report.database -ne 'arthiq_olist' -or $report.reader_role -ne 'arthiq_olist_analytics' -or
        $report.reader_privileges_verified -ne $true -or $report.rejected_rows -ne 0 -or $report.skipped_rows -ne 0) {
        throw 'Missing or unexpected post-commit verification result.'
    }
    $counts = foreach ($table in $tables) {
        $row = $report.$table
        if ($null -eq $row.csv_rows -or $row.pg_rows -ne $row.csv_rows) { throw "Row reconciliation failed for $table." }
        [pscustomobject]@{Table=$table; CSV=$row.csv_rows; PostgreSQL=$row.pg_rows}
    }
    $foreignKeys = @($report.constraints | Where-Object { $_.definition -like 'FOREIGN KEY*' })
    if ($foreignKeys.Count -ne 6) { throw 'Expected six verified foreign keys.' }

    Write-Host "Verified: $($report.mode) in $($report.database) ($($report.elapsed_seconds) seconds)"
    $counts | Format-Table -AutoSize | Out-Host
    Write-Host 'Foreign keys:'
    $foreignKeys | Select-Object table, definition | Format-Table -AutoSize -Wrap | Out-Host
    Write-Host 'Reader permission checks passed: arthiq_olist_analytics. Skipped: 0. Rejected: 0.'
    Write-Host 'Full post-commit PostgreSQL report:'
    Write-Output $json
}

try {
    $tables = @(Get-ImportInputs)
    Write-Host 'Nine CSVs found. Connecting to arthiq_olist as postgres at 127.0.0.1:5432.'
    Write-Host 'Enter the PostgreSQL password at the hidden psql prompt. Import and verification may take several minutes.'
    $stage = Join-Path ([IO.Path]::GetTempPath()) ('olist-copy-' + [guid]::NewGuid())
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    try {
        New-OlistCopyDriver (Join-Path $PSScriptRoot 'run_in_psql.sql') $stage
        $json = Invoke-OlistPsql $stage
        Show-Verification $json $tables
        if ($ReportPath) { [IO.File]::WriteAllText($ReportPath, $json) }
    } finally {
        # Only files created in this invocation's new private staging directory.
        foreach ($file in [IO.Directory]::GetFiles($stage)) { [IO.File]::Delete($file) }
        [IO.Directory]::Delete($stage)
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
