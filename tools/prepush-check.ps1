$root=(git rev-parse --show-toplevel).Trim()
$bad=@()
Get-ChildItem -LiteralPath $root -Recurse -File -Filter 'REVIVAL_REPORT.md' -ErrorAction SilentlyContinue | ForEach-Object {
    $t=Get-Content $_.FullName -Raw
    if($t -notmatch '\b(READY|READY_WITH_REVIEW_ITEMS|ESCALATION_REQUIRED|READY_FOR_LIVE_TEST|LIVE_VALIDATED|SUPERSEDED|ESCALATED)\b'){$bad+=$_.FullName}
}
if($bad){Write-Error ("Invalid report status:`n"+($bad -join "`n")); exit 11}

# Fast cross-cutting tests plus the tests of the modules this branch touched (ROADMAP-3 item 80.1). Keep this list in step with
# CROSS_CUTTING_TESTS in bridgeforge/merge_train.py (tests/test_merge_train.py checks it).
$crossCutting=@('tests.test_probe_contract','tests.test_safeio_ratchet','tests.test_source_paths','tests.test_checks_index','tests.test_cli_golden','tests.test_test_guard')
# Prefer the project venv (this checkout's, else the main checkout's when this is a worktree): a system Python with an
# editable bridgeforge install imports that checkout's code ahead of this one, so the tests would check the wrong tree.
$py=$null
$common=(git rev-parse --path-format=absolute --git-common-dir).Trim()
$venvs=@((Join-Path $root '.venv\Scripts\python.exe'), (Join-Path (Split-Path $common -Parent) '.venv\Scripts\python.exe'))
foreach($c in @($venvs + @('python','py','C:\Users\exxec\AppData\Local\Python\pythoncore-3.14-64\python.exe'))){
    $cmd=Get-Command $c -ErrorAction SilentlyContinue
    if(-not $cmd){continue}
    & $cmd.Source -c 'import sys' *> $null
    if($LASTEXITCODE -eq 0){$py=$cmd.Source;break}
}
if(-not $py){Write-Host 'Pre-push validation: PASS (report check only; no Python found, tests skipped)'; exit 0}
$modules=@($crossCutting)
git -C $root rev-parse --verify --quiet origin/main *> $null
if($LASTEXITCODE -eq 0){
    $changed=@(git -C $root diff --name-only origin/main...HEAD)
    foreach($f in $changed){
        if($f -match '^bridgeforge/(?:[A-Za-z0-9_]+/)*([A-Za-z0-9_]+)\.py$'){
            $name=$Matches[1]
            $testsRoot=Join-Path $root 'tests'
            Get-ChildItem -LiteralPath $testsRoot -Recurse -File -Filter "test_$name*.py" -ErrorAction SilentlyContinue | Where-Object {
                $_.FullName -notmatch '[\\/]__pycache__[\\/]'
            } | Sort-Object FullName | ForEach-Object {
                $relative=$_.FullName.Substring($testsRoot.Length+1)
                $modules+=('tests.'+($relative -replace '\.py$','' -replace '[\\/]','.'))
            }
        }
    }
}
$modules=@($modules | Select-Object -Unique)
# Git runs hooks with GIT_DIR and friends pointing at this repository; tests that `git init` a temp folder would otherwise
# re-initialise the real one (set core.bare=true, 2026-10-21). Clear them for the test run only.
Get-ChildItem Env: | Where-Object { $_.Name -like 'GIT_*' } | ForEach-Object { Remove-Item -LiteralPath ("Env:" + $_.Name) }
Push-Location $root
try{ & $py -m unittest @modules -q; $testExit=$LASTEXITCODE }finally{Pop-Location}
if($testExit -ne 0){Write-Error 'Pre-push tests failed; fix them before pushing.'; exit 13}
Write-Host ("Pre-push validation: PASS ("+$modules.Count+" test modules)")
