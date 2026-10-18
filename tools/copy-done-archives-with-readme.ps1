# Copy each Done ZIP with a README derived from its folder's ARCHIVE_NOTE.md.
# Keep one current README ZIP per mod at the top of Done, using its release name.
# Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/copy-done-archives-with-readme.ps1 [-DonePath <path>] [-Quiet]
param(
    [string]$DonePath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'Done'),
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$utf8 = [Text.UTF8Encoding]::new($false)
$done = (Resolve-Path -LiteralPath $DonePath).Path
$checkpoint = Join-Path $done '.copy-done-archives-with-readme.partial.jsonl'
$unreadableReadmes = [Collections.Generic.List[string]]::new()

function Same-Bytes([byte[]]$a, [byte[]]$b) {
    if ($null -eq $a -or $null -eq $b) { return $false }
    if ($a.Length -ne $b.Length) { return $false }
    for ($i = 0; $i -lt $a.Length; $i++) { if ($a[$i] -ne $b[$i]) { return $false } }
    return $true
}

function Read-Zip-Entry([IO.Compression.ZipArchive]$archive, [string]$name) {
    $entry = $archive.GetEntry($name)
    if ($null -eq $entry) { return $null }
    $stream = $entry.Open()
    $memory = [IO.MemoryStream]::new()
    try { $stream.CopyTo($memory); return $memory.ToArray() }
    finally { $stream.Dispose(); $memory.Dispose() }
}

function Test-Copy([string]$source, [string]$copy, [byte[]]$readmeBytes) {
    if (-not (Test-Path -LiteralPath $copy)) { return $false }
    if ((Get-Item -LiteralPath $copy).LastWriteTimeUtc -lt (Get-Item -LiteralPath $source).LastWriteTimeUtc) { return $false }
    $original = [IO.Compression.ZipFile]::OpenRead($source)
    try {
        $archive = [IO.Compression.ZipFile]::OpenRead($copy)
        try {
            if (-not (Same-Bytes (Read-Zip-Entry $archive 'readme.txt') $readmeBytes)) { return $false }
            $sourceEntries = @($original.Entries | Where-Object { $_.FullName -notmatch '(?i)^readme\.txt$' } | ForEach-Object { "$($_.FullName):$($_.Length)" } | Sort-Object)
            $copyEntries = @($archive.Entries | Where-Object { $_.FullName -notmatch '(?i)^readme\.txt$' } | ForEach-Object { "$($_.FullName):$($_.Length)" } | Sort-Object)
            return -not [bool](Compare-Object $sourceEntries $copyEntries)
        } finally { $archive.Dispose() }
    } finally { $original.Dispose() }
}

$folders = @(Get-ChildItem -LiteralPath $done -Directory | Where-Object { -not $_.Name.StartsWith('_') } | Sort-Object Name)
$jobs = @(
    foreach ($folder in $folders) {
        $note = Join-Path $folder.FullName 'ARCHIVE_NOTE.md'
        if (-not (Test-Path -LiteralPath $note)) { throw "Missing ARCHIVE_NOTE.md: $($folder.FullName)" }
        foreach ($zip in Get-ChildItem -LiteralPath $folder.FullName -File -Filter '*.zip' | Where-Object { $_.BaseName -notmatch '(?i)-with-readme$' -and $_.BaseName -notmatch '(?i)\.partial$' } | Sort-Object Name) {
            [pscustomobject]@{ Folder = $folder; Note = $note; Source = $zip }
        }
    }
)
$currentReleases = @(
    foreach ($folder in $folders) {
        $matches = @($jobs | Where-Object { $_.Folder.FullName -eq $folder.FullName -and $_.Source.BaseName -notmatch '(?i)-original-descriptions$' })
        if ($matches.Count -ne 1) { throw "Expected one current release ZIP in $($folder.FullName), found $($matches.Count)" }
        $matches[0]
    }
)

[IO.File]::WriteAllText($checkpoint, ((@{ input = $done; sourceArchives = $jobs.Count } | ConvertTo-Json -Compress) + "`n"), $utf8)
$finished = $false
try {
    $index = 0
    foreach ($job in $jobs) {
        $index++
        $started = Get-Date
        $source = $job.Source.FullName
        $copy = Join-Path $job.Folder.FullName ($job.Source.BaseName + '-with-readme.zip')
        $readme = Join-Path $job.Folder.FullName 'readme.txt'
        $body = [IO.File]::ReadAllText($job.Note, [Text.Encoding]::UTF8)
        $body = [regex]::Replace($body, '(?ms)^## Contents[ \t]*\r?\n.*?(?=^#{1,2} |\z)', '')
        $bytes = $utf8.GetBytes($body.TrimEnd() + "`r`n")
        $readmeCurrent = $false
        if (Test-Path -LiteralPath $readme) {
            try { $readmeCurrent = Same-Bytes ([IO.File]::ReadAllBytes($readme)) $bytes }
            catch [UnauthorizedAccessException] {
                # A prior run may have created this file with an inaccessible ACL.
                # We can still verify the derived README inside each ZIP copy.
                $unreadableReadmes.Add($readme)
                $readmeCurrent = $true
            }
        }
        if (-not $readmeCurrent) { [IO.File]::WriteAllBytes($readme, $bytes) }
        $status = 'already current'
        if (-not (Test-Copy $source $copy $bytes)) {
            $temp = Join-Path $job.Folder.FullName ($job.Source.BaseName + '.' + [guid]::NewGuid().ToString('N') + '.partial.zip')
            $backup = $copy + '.backup'
            Copy-Item -LiteralPath $source -Destination $temp
            try {
                $archive = [IO.Compression.ZipFile]::Open($temp, [IO.Compression.ZipArchiveMode]::Update)
                try {
                    foreach ($entry in @($archive.Entries | Where-Object { $_.FullName -match '(?i)^readme\.txt$' })) { $entry.Delete() }
                    $entry = $archive.CreateEntry('readme.txt', [IO.Compression.CompressionLevel]::Optimal)
                    $stream = $entry.Open()
                    try { $stream.Write($bytes, 0, $bytes.Length) }
                    finally { $stream.Dispose() }
                } finally { $archive.Dispose() }
                if (-not (Test-Copy $source $temp $bytes)) { throw "ZIP README verification failed: $temp" }
                if (Test-Path -LiteralPath $backup) { throw "Backup already exists: $backup" }
                if (Test-Path -LiteralPath $copy) { Move-Item -LiteralPath $copy -Destination $backup }
                try { Move-Item -LiteralPath $temp -Destination $copy }
                catch { if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $copy }; throw }
                if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
                $status = 'copied'
            } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force } }
        }
        [IO.File]::AppendAllText($checkpoint, ((@{ source = $source; output = $copy; status = $status } | ConvertTo-Json -Compress) + "`n"), $utf8)
        if (-not $Quiet) { Write-Output "[$index/$($jobs.Count)] $($job.Folder.Name): $($job.Source.Name) $status ($([math]::Round(((Get-Date) - $started).TotalSeconds, 1))s)" }
    }
    $index = 0
    foreach ($job in $currentReleases) {
        $index++
        $started = Get-Date
        $source = Join-Path $job.Folder.FullName ($job.Source.BaseName + '-with-readme.zip')
        $copy = Join-Path $done $job.Source.Name
        $legacyCopy = Join-Path $done ($job.Source.BaseName + '-with-readme.zip')
        $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
        $status = 'already current'
        if (-not (Test-Path -LiteralPath $copy) -or (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne $sourceHash) {
            $temp = Join-Path $done ($job.Source.Name + '.' + [guid]::NewGuid().ToString('N') + '.partial')
            $backup = $copy + '.backup'
            Copy-Item -LiteralPath $source -Destination $temp
            try {
                if ((Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash -ne $sourceHash) { throw "Root copy mismatch: $temp" }
                if (Test-Path -LiteralPath $backup) { throw "Backup already exists: $backup" }
                if (Test-Path -LiteralPath $copy) { Move-Item -LiteralPath $copy -Destination $backup }
                try { Move-Item -LiteralPath $temp -Destination $copy }
                catch { if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $copy }; throw }
                if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
            } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force } }
            $status = 'copied to Done'
        }
        # Remove only the exact legacy name after the release-named ZIP is verified.
        if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne $sourceHash) { throw "Final root ZIP mismatch: $copy" }
        if (Test-Path -LiteralPath $legacyCopy) {
            Remove-Item -LiteralPath $legacyCopy -Force
            $status += '; removed old name'
        }
        [IO.File]::AppendAllText($checkpoint, ((@{ source = $source; output = $copy; status = $status } | ConvertTo-Json -Compress) + "`n"), $utf8)
        if (-not $Quiet) { Write-Output "[$index/$($currentReleases.Count)] $($job.Folder.Name): root archive $status ($([math]::Round(((Get-Date) - $started).TotalSeconds, 1))s)" }
    }
    $finished = $true
} finally {
    if ($finished) { Remove-Item -LiteralPath $checkpoint -Force }
}
if ($unreadableReadmes.Count -gt 0) {
    Write-Warning "$($unreadableReadmes.Count) existing README file(s) could not be read. ZIP copies were checked using ARCHIVE_NOTE.md. The inaccessible files were left unchanged; their permissions need repair before the script can update them."
}
