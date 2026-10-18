# Build Done/MASTER_LOG.md from each archived mod's note, mod_info and release ZIP.
param(
    [string]$DonePath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'Done'),
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$done = (Resolve-Path -LiteralPath $DonePath).Path
$utf8 = [Text.UTF8Encoding]::new($false)
$output = Join-Path $done 'MASTER_LOG.md'
$checkpoint = Join-Path $done '.master-log.partial.jsonl'
$folders = @(Get-ChildItem -LiteralPath $done -Directory | Where-Object { -not $_.Name.StartsWith('_') } | Sort-Object Name)

function Get-Version([string]$path) {
    $raw = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $match = [regex]::Match($raw, '(?s)"version"\s*:\s*(?:"([^"]+)"|\{([^}]+)\})')
    if ($match.Groups[1].Success) { return $match.Groups[1].Value }
    if ($match.Groups[2].Success) {
        $parts = foreach ($key in @('major', 'minor', 'patch')) {
            [regex]::Match($match.Groups[2].Value, '"' + $key + '"\s*:\s*"?([^",\s}]+)').Groups[1].Value
        }
        if (@($parts | Where-Object { -not $_ }).Count -eq 0) { return ($parts -join '.') }
    }
    throw "Could not read release version: $path"
}

function Get-Work([string]$note, [string]$folder) {
    $counts = [regex]::Match($note, '(\d+) shipped file\(s\) changed and (\d+) added')
    if ($counts.Success) {
        $changed = [int]$counts.Groups[1].Value
        $added = [int]$counts.Groups[2].Value
        $paths = @([regex]::Matches($note, '(?m)^- (?:changed|added): `([^`]+)`') | ForEach-Object { $_.Groups[1].Value })
        if ($paths.Count -gt $changed + $added) { throw "Listed files exceed change count: $folder" }
        if ($paths.Count -le 3) { return "$changed changed, $added added: $(($paths | ForEach-Object { '`' + $_ + '`' }) -join ', ')" }
        $areas = [Collections.Generic.List[string]]::new()
        if (@($paths | Where-Object { $_ -eq 'mod_info.json' }).Count) { $areas.Add('metadata') }
        if (@($paths | Where-Object { $_ -match '(?i)\.jar$|\.class$|\.java$' }).Count) { $areas.Add('code/JAR') }
        if (@($paths | Where-Object { $_ -like 'data/*' }).Count) { $areas.Add('game data') }
        if (@($paths | Where-Object { $_ -match '^(?i:graphics|sounds)/' }).Count) { $areas.Add('assets') }
        if ($areas.Count -eq 0) { $areas.Add('other files') }
        $detail = if ($paths.Count -lt $changed + $added) { 'see report for full file list' } else { 'see note for file list' }
        return "$changed changed, $added added ($($areas -join ', ')); $detail"
    }
    switch ($folder) {
        'Arkgneisis' { return 'RC8 jar relink and compatibility work; original archive lacks an unpacked file baseline; see report' }
        'BF-Legacy-Fleets' { return 'Built BridgeForge legacy fleet API library; no original file baseline was retained' }
        'ClearCommands' { return 'Updated RC8 metadata; removed bundled source archive from mod folder; shipped JAR unchanged' }
        'Nightcross' { return 'RC8 revival; original archive lacks an unpacked file baseline; see report' }
        'Omega-Trauma' { return 'RC8 revival; original archive lacks an unpacked file baseline; see report' }
        'RevenantLib' { return 'Snapshot of legacy API bridges and Xenoargh content; see provenance' }
        default { throw "No file-diff summary or exception rule: $folder" }
    }
}

$inputs = @($folders | ForEach-Object {
    $note = Join-Path $_.FullName 'ARCHIVE_NOTE.md'
    $modInfo = Join-Path (Join-Path $_.FullName $_.Name) 'mod_info.json'
    if (-not (Test-Path -LiteralPath $note)) { throw "Missing archive note: $note" }
    if (-not (Test-Path -LiteralPath $modInfo)) { throw "Missing mod_info.json: $modInfo" }
    "$($_.Name):$((Get-FileHash -LiteralPath $note -Algorithm SHA256).Hash):$((Get-FileHash -LiteralPath $modInfo -Algorithm SHA256).Hash)"
})
$rootPackages = @(Get-ChildItem -LiteralPath $done -File -Filter '*.zip' | Sort-Object Name | ForEach-Object { $_.Name })
$header = @{ inputs = $inputs; rootPackages = $rootPackages }
$headerLine = ConvertTo-Json $header -Compress -Depth 3
$saved = @{}
if (Test-Path -LiteralPath $checkpoint) {
    $lines = @(Get-Content -LiteralPath $checkpoint)
    if ($lines.Count -gt 0 -and $lines[0] -eq $headerLine) {
        foreach ($line in $lines | Select-Object -Skip 1) {
            try { $row = $line | ConvertFrom-Json; $saved[$row.folder] = $row }
            catch { } # Ignore a truncated final line after interruption.
        }
    } else { [IO.File]::WriteAllText($checkpoint, $headerLine + "`n", $utf8) }
} else { [IO.File]::WriteAllText($checkpoint, $headerLine + "`n", $utf8) }

$index = 0
$rows = @(
    foreach ($folder in $folders) {
        $index++
        $started = Get-Date
        if ($saved.ContainsKey($folder.Name)) {
            if (-not $Quiet) { [Console]::Error.WriteLine("[$index/$($folders.Count)] $($folder.Name): from checkpoint") }
            $saved[$folder.Name]
            continue
        }
        $notePath = Join-Path $folder.FullName 'ARCHIVE_NOTE.md'
        $note = [IO.File]::ReadAllText($notePath, [Text.Encoding]::UTF8)
        $modInfo = Join-Path (Join-Path $folder.FullName $folder.Name) 'mod_info.json'
        if (-not (Test-Path -LiteralPath $modInfo)) { throw "Missing mod_info.json: $modInfo" }
        $version = Get-Version $modInfo
        # Prefer the package named in this note, avoiding similarly prefixed mod names.
        $named = [regex]::Matches($note, '(?m)^- `([^`]+\.zip)` - the same folder, zipped\.')
        if ($named.Count -ne 1) { throw "Expected one current package in archive note: $($folder.Name)" }
        $package = $named[0].Groups[1].Value
        $packagePresent = Test-Path -LiteralPath (Join-Path $done $package)
        $badNamedCopy = if (-not $packagePresent -and (Test-Path -LiteralPath (Join-Path $done ('(bad) ' + $package)))) { '(bad) ' + $package } else { '' }
        $date = [regex]::Match($note, '(?i)archived\s+(\d{4}-\d{2}-\d{2})').Groups[1].Value
        $dateBasis = 'archive'
        if (-not $date -and $folder.Name -eq 'ClearCommands') { $date = '2026-09-27'; $dateBasis = 'live validation' }
        if (-not $date -and $folder.Name -eq 'RevenantLib') {
            $date = [regex]::Match($note, 'archive snapshot \((\d{4}-\d{2}-\d{2})\)').Groups[1].Value
            $dateBasis = 'snapshot'
        }
        if (-not $date) { throw "No recorded date: $($folder.Name)" }
        $status = [regex]::Match($note, 'Revival report status:\s*\*\*(.*?)\*\*').Groups[1].Value
        if (-not $status -and $folder.Name -eq 'ClearCommands') { $status = 'LIVE_VALIDATED' }
        if (-not $status -and $folder.Name -eq 'RevenantLib') { $status = 'SNAPSHOT' }
        if (-not $status) { throw "No status: $($folder.Name)" }
        $work = Get-Work $note $folder.Name
        $row = [pscustomobject]@{ folder = $folder.Name; version = $version; date = $date; dateBasis = $dateBasis; status = $status; work = $work; package = $package; packagePresent = $packagePresent; badNamedCopy = $badNamedCopy }
        [IO.File]::AppendAllText($checkpoint, (($row | ConvertTo-Json -Compress) + "`n"), $utf8)
        if (-not $Quiet) { [Console]::Error.WriteLine("[$index/$($folders.Count)] $($folder.Name): $version ($([math]::Round(((Get-Date) - $started).TotalSeconds, 1))s)") }
        $row
    }
)

$text = [Collections.Generic.List[string]]::new()
$text.Add('# Done: master revival log')
$text.Add('')
$text.Add('One row per archived mod folder in `Done/`. Versions come from each shipped `mod_info.json`; package names and work summaries come from that mod''s `ARCHIVE_NOTE.md`. The date is the recorded archive date, except ClearCommands (dated live validation) and RevenantLib (dated snapshot). It is not a claim that every listed change happened on that date. Follow each note and report for the exact work and evidence.')
$text.Add('')
$text.Add('| Mod | Release version | Recorded date | Status | Work recorded | Package and details |')
$text.Add('| --- | --- | --- | --- | --- | --- |')
foreach ($row in $rows) {
    $folder = $row.folder
    $report = Join-Path (Join-Path $done $folder) 'workspace\REVIVAL_REPORT.md'
    $details = "[note]($folder/ARCHIVE_NOTE.md)"
    if (Test-Path -LiteralPath $report) { $details += ", [report]($folder/workspace/REVIVAL_REPORT.md)" }
    elseif ($folder -eq 'RevenantLib') { $details += ", [provenance]($folder/workspace/PROVENANCE.md)" }
    if ($row.packagePresent) { $details = "[$($row.package)]($($row.package)); $details" }
    else {
        $details = "**Missing top-level package:** ``$($row.package)``; $details"
        if ($row.badNamedCopy) { $details += "; present as ``$($row.badNamedCopy)`` (marked bad)" }
    }
    $work = $row.work.Replace('|', '\|')
    $text.Add("| $folder | $($row.version) | $($row.date) | $($row.status) | $work | $details |")
}
$text.Add('')
$present = @($rows | Where-Object { $_.packagePresent }).Count
$text.Add("Total: $($rows.Count) archived mod folders; $present named top-level release ZIPs present. Generated from local evidence; run ``tools/build-done-master-log.ps1`` after archiving another mod.")
$text.Add('')
[IO.File]::WriteAllText($output, ($text -join "`r`n"), $utf8)
Remove-Item -LiteralPath $checkpoint -Force
if (-not $Quiet) { Write-Output "Wrote $output ($($rows.Count) releases)" }
