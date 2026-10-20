$root=(git rev-parse --show-toplevel).Trim()
$bad=@()
Get-ChildItem -LiteralPath $root -Recurse -File -Filter 'REVIVAL_REPORT.md' -ErrorAction SilentlyContinue | ForEach-Object {
    $t=Get-Content $_.FullName -Raw
    if($t -notmatch '\b(READY|READY_WITH_REVIEW_ITEMS|ESCALATION_REQUIRED|READY_FOR_LIVE_TEST|LIVE_VALIDATED|SUPERSEDED|ESCALATED)\b'){$bad+=$_.FullName}
}
if($bad){Write-Error ("Invalid report status:`n"+($bad -join "`n")); exit 11}
Write-Host 'Pre-push validation: PASS'
