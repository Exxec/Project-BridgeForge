$root=(git rev-parse --show-toplevel).Trim()
$staged=@(git diff --cached --name-only --diff-filter=ACMR)
$blocked=@()
foreach($r in $staged){
    $n=$r.Replace('/','\')
    if($n -match '(^|\\)(build|out|target|classes|bin)(\\|$)'){$blocked+=$r}
}
if($blocked){Write-Error ("Blocked build artifacts:`n"+($blocked -join "`n")); exit 10}
Push-Location $root
# The project .venv Python has no ruff (found 2026-10-05): use the first interpreter that does, else say how to get it.
$py=$null
foreach($c in @('python','py','C:\Users\exxec\AppData\Local\Python\pythoncore-3.14-64\python.exe')){
    $cmd=Get-Command $c -ErrorAction SilentlyContinue
    if(-not $cmd){continue}
    & $cmd.Source -m ruff --version *> $null
    if($LASTEXITCODE -eq 0){$py=$cmd.Source;break}
}
# No Python with ruff (2026-11-15: the 3.14 install above is gone): uvx runs ruff without installing it anywhere.
$uvx=Get-Command uvx -ErrorAction SilentlyContinue
if(-not $py -and -not $uvx){Write-Error 'No Python with ruff and no uvx found. Run: python -m pip install ruff (or install uv).'; exit 12}
# Lint what is being committed (ROADMAP 77.25): untracked agent scratch must not block unrelated commits. CI still lints the
# whole repository.
$pyFiles=@($staged | Where-Object { $_ -like '*.py' -and (Test-Path -LiteralPath $_) })
if(-not $pyFiles){ Pop-Location; Write-Host 'Pre-commit validation: PASS (no staged Python files)'; exit 0 }
# pyproject's required-version pins ruff (96.5 C8): uvx runs exactly that one, an installed ruff must match it.
$ruffPin=(Select-String -LiteralPath (Join-Path $root 'pyproject.toml') -Pattern '^required-version = "==(.+)"$').Matches | ForEach-Object { $_.Groups[1].Value } | Select-Object -First 1
try{ if($uvx -and $ruffPin){ & $uvx.Source "ruff@$ruffPin" check -- @pyFiles }elseif($py){ & $py -m ruff check -- @pyFiles }else{ & $uvx.Source ruff check -- @pyFiles }; $ruffExit=$LASTEXITCODE }finally{Pop-Location}
if($ruffExit -ne 0){Write-Error 'ruff check failed; fix lint before committing.'; exit 11}
# Generated docs (ROADMAP-3 96.5 C1): a staged test that names a finding id, or a changed --help text, makes docs/CHECKS.md or
# docs/COMMANDS.md stale, which only the full suite and CI noticed (2026-11-17). docs-index --check writes nothing.
$venvs=@((Join-Path $root '.venv\Scripts\python.exe'), (Join-Path (Split-Path (git rev-parse --path-format=absolute --git-common-dir).Trim() -Parent) '.venv\Scripts\python.exe'))
$venvPy=$venvs | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if(-not $venvPy){ Write-Host 'Pre-commit validation: PASS (no project .venv: generated docs not checked)'; exit 0 }
Get-ChildItem Env: | Where-Object { $_.Name -like 'GIT_*' } | ForEach-Object { Remove-Item -LiteralPath ("Env:" + $_.Name) }
Push-Location $root
try{ & $venvPy -m bridgeforge docs-index --check *> $null; $docsExit=$LASTEXITCODE }finally{Pop-Location}
if($docsExit -ne 0){Write-Error 'docs/CHECKS.md or docs/COMMANDS.md is stale: run "python -m bridgeforge docs-index" (and "python -m tests.test_cli_golden --write" after a --help change), review and stage them.'; exit 14}
Write-Host 'Pre-commit validation: PASS'
