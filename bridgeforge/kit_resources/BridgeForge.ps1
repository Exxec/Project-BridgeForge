param(
    [string]$Python = "python",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$BridgeForgeArguments
)
$priorPythonPath = $env:PYTHONPATH
try {
    & $Python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,15) else 2)'
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'This trial profile requires Python 3.15.'
        exit 2
    }
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'runtime'
    & $Python -m bridgeforge @BridgeForgeArguments
    $bridgeForgeExit = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $priorPythonPath
}
exit $bridgeForgeExit
