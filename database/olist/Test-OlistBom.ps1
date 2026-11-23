# Run with Windows PowerShell. Uses synthetic fixtures, no database connection.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Normalize-OlistCopy.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('olist-bom-test-' + [guid]::NewGuid())
$stage = Join-Path $root stage
[IO.Directory]::CreateDirectory($stage) | Out-Null
try {
    $utf8 = [Text.UTF8Encoding]::new($false)
    $bytes = $utf8.GetBytes("name,value`r`n`"café`r`nline`",1.00`r`n")
    $bomFile = Join-Path $root bom.csv
    $plainFile = Join-Path $root plain.csv
    $withBom = [byte[]](@(0xEF,0xBB,0xBF) + $bytes)
    [IO.File]::WriteAllBytes($bomFile,$withBom)
    [IO.File]::WriteAllBytes($plainFile,$bytes)
    $sql = "\copy pg_temp.src_a (name,value) FROM '$bomFile' WITH (FORMAT CSV, HEADER MATCH)`n\copy pg_temp.src_b (name,value) FROM '$plainFile' WITH (FORMAT CSV, HEADER MATCH)"
    $driver = Join-Path $root source.sql
    [IO.File]::WriteAllText($driver,$sql)
    New-OlistCopyDriver $driver $stage
    if ([IO.File]::ReadAllText((Join-Path $stage run_in_psql.sql)) -cne $sql.Replace($bomFile,'bom.csv')) { throw 'Unexpected COPY rewrite' }
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $stage bom.csv))) -cne [Convert]::ToBase64String($bytes)) { throw 'Payload bytes changed' }
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($bomFile)) -cne [Convert]::ToBase64String($withBom)) { throw 'Source changed' }
    if (Test-Path (Join-Path $stage plain.csv)) { throw 'Plain file was copied' }
    Write-Output 'BOM regression passed.'
} finally {
    foreach ($dir in @($stage,$root)) {
        foreach ($file in [IO.Directory]::GetFiles($dir)) { [IO.File]::Delete($file) }
        [IO.Directory]::Delete($dir)
    }
}
