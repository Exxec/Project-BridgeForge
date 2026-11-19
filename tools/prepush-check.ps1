$root=(git rev-parse --show-toplevel).Trim()
$clock=[System.Diagnostics.Stopwatch]::StartNew()
$budgetSeconds=120  # ROADMAP-3 96.5 C5: a push should be checked in under 2 minutes; CI runs everything
$bad=@()
Get-ChildItem -LiteralPath $root -Recurse -File -Filter 'REVIVAL_REPORT.md' -ErrorAction SilentlyContinue | ForEach-Object {
    $t=Get-Content $_.FullName -Raw
    if($t -notmatch '\b(READY|READY_WITH_REVIEW_ITEMS|ESCALATION_REQUIRED|READY_FOR_LIVE_TEST|LIVE_VALIDATED|SUPERSEDED|ESCALATED)\b'){$bad+=$_.FullName}
}
if($bad){Write-Error ("Invalid report status:`n"+($bad -join "`n")); exit 11}

# Prefer the project venv (this checkout's, else the main checkout's when this is a worktree): a system Python with an
# editable bridgeforge install imports that checkout's code ahead of this one, so the tests would check the wrong tree.
$py=$null
$common=(git rev-parse --path-format=absolute --git-common-dir).Trim()
$venvs=@((Join-Path $root '.venv\Scripts\python.exe'), (Join-Path (Split-Path $common -Parent) '.venv\Scripts\python.exe'))
foreach($c in @($venvs + @('python','py'))){
    $cmd=Get-Command $c -ErrorAction SilentlyContinue
    if(-not $cmd){continue}
    & $cmd.Source -c 'import sys' *> $null
    if($LASTEXITCODE -eq 0){$py=$cmd.Source;break}
}
if(-not $py){Write-Host 'Pre-push validation: PASS (report check only; no Python found, tests skipped)'; exit 0}

$changed=@()
git -C $root rev-parse --verify --quiet origin/main *> $null
if($LASTEXITCODE -eq 0){ $changed=@(git -C $root diff --name-only origin/main...HEAD) }

# Git runs hooks with GIT_DIR and friends pointing at this repository; tests that `git init` a temp folder would otherwise
# re-initialise the real one (set core.bare=true, 2026-10-21). Clear them for the checks below.
Get-ChildItem Env: | Where-Object { $_.Name -like 'GIT_*' } | ForEach-Object { Remove-Item -LiteralPath ("Env:" + $_.Name) }
Push-Location $root
try{
    # Static tier first (96.5 C5): seconds, and it catches what a commit made with the hooks off let through.
    $pyFiles=@($changed | Where-Object { $_ -like '*.py' -and (Test-Path -LiteralPath $_) })
    if($pyFiles){
        $uvx=Get-Command uvx -ErrorAction SilentlyContinue
        $ruffPin=(Select-String -LiteralPath (Join-Path $root 'pyproject.toml') -Pattern '^required-version = "==(.+)"$').Matches | ForEach-Object { $_.Groups[1].Value } | Select-Object -First 1
        if($uvx -and $ruffPin){ & $uvx.Source "ruff@$ruffPin" check -- @pyFiles }
        else{ & $py -m ruff --version *> $null
        if($LASTEXITCODE -eq 0){ & $py -m ruff check -- @pyFiles }elseif($uvx){ & $uvx.Source ruff check -- @pyFiles }else{ $global:LASTEXITCODE=0; Write-Host 'pre-push: no ruff (no uvx); lint skipped' } }
        if($LASTEXITCODE -ne 0){Write-Error 'ruff check failed on the changed files; fix lint before pushing.'; exit 12}
    }
    & $py -m bridgeforge docs-index --check *> $null
    if($LASTEXITCODE -ne 0){Write-Error 'docs/CHECKS.md or docs/COMMANDS.md is stale: run "python -m bridgeforge docs-index", review and commit.'; exit 14}
    $static=$clock.Elapsed.TotalSeconds
    # Tests: the cross-cutting ones plus those named after or importing a changed module (bridgeforge.merge_train.select_test_modules),
    # without the cases tests/slow_tests.json lists (CI's slow partition runs them).
    $modules=@(& $py (Join-Path $root 'tools\prepush-select.py') @changed)
    if($LASTEXITCODE -ne 0 -or -not $modules){Write-Error 'tools/prepush-select.py failed to choose the tests.'; exit 15}
    & $py (Join-Path $root 'tests\run_partitioned.py') --partition fast --modules @modules; $testExit=$LASTEXITCODE
}finally{Pop-Location}
if($testExit -ne 0){Write-Error 'Pre-push tests failed; fix them before pushing.'; exit 13}
$total=$clock.Elapsed.TotalSeconds
$note=if($total -gt $budgetSeconds){" - over the ${budgetSeconds} s budget"}else{''}
Write-Host ("Pre-push validation: PASS ({0} test modules; static {1:N0} s, total {2:N0} s{3})" -f $modules.Count, $static, $total, $note)
