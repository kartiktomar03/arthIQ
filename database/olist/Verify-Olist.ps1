param([string]$ReportPath)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../..')
$psql = Join-Path $env:ProgramFiles 'PostgreSQL/19/bin/psql.exe'
Write-Host 'First prompt: local postgres administrator password. The check only sets a reader password if missing.'
& $psql -X -W -h 127.0.0.1 -p 5432 -U postgres -d arthiq_olist -f database/olist/check_reader_password.psql
if ($LASTEXITCODE -ne 0) {exit 1}
# getpass reads from the Windows console. Only verification stdout goes to the report.
if ($ReportPath) {
    & .\.venv\Scripts\python.exe -m evaluation.verify_olist --prompt | Tee-Object -FilePath $ReportPath
} else {
    & .\.venv\Scripts\python.exe -m evaluation.verify_olist --prompt
}
exit $LASTEXITCODE
