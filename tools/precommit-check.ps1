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
if(-not $py){Write-Error 'No Python with ruff found. Run: python -m pip install ruff (or put the interpreter that has it first on PATH).'; exit 12}
# Lint what is being committed (ROADMAP 77.25): untracked agent scratch must not block unrelated commits. CI still lints the
# whole repository.
$pyFiles=@($staged | Where-Object { $_ -like '*.py' -and (Test-Path -LiteralPath $_) })
if(-not $pyFiles){ Pop-Location; Write-Host 'Pre-commit validation: PASS (no staged Python files)'; exit 0 }
try{ & $py -m ruff check -- @pyFiles ; $ruffExit=$LASTEXITCODE }finally{Pop-Location}
if($ruffExit -ne 0){Write-Error 'ruff check failed; fix lint before committing.'; exit 11}
Write-Host 'Pre-commit validation: PASS'
