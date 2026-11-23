# Stage only BOM-prefixed input files. Byte copying after the signature preserves
# repeated rows, embedded quotes/newlines, and the original decimal spellings.
function New-OlistCopyDriver([string]$SourceDriver, [string]$StageDirectory) {
    $utf8 = [Text.UTF8Encoding]::new($false, $true)
    $driver = [IO.File]::ReadAllText($SourceDriver, $utf8)
    $pattern = "(?im)^(\\copy\s+pg_temp\.src_\w+\s+[^\r\n]*?\sFROM\s+')([^']+)(')"
    $driver = [regex]::Replace($driver, $pattern, {
        param($match)
        $path = $match.Groups[2].Value
        $inputFile = [IO.File]::OpenRead($path)
        try {
            if ($inputFile.ReadByte() -ne 0xEF -or $inputFile.ReadByte() -ne 0xBB -or $inputFile.ReadByte() -ne 0xBF) {
                return $match.Value
            }
            $name = [IO.Path]::GetFileName($path)
            $outputFile = [IO.File]::Open((Join-Path $StageDirectory $name), [IO.FileMode]::CreateNew)
            try { $inputFile.CopyTo($outputFile) } finally { $outputFile.Dispose() }
            # psql's working directory is the staging directory.
            return $match.Groups[1].Value + $name + $match.Groups[3].Value
        } finally { $inputFile.Dispose() }
    })
    [IO.File]::WriteAllText((Join-Path $StageDirectory 'run_in_psql.sql'), $driver, $utf8)
}
