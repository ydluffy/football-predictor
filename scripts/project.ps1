[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("test", "train", "api", "web-lint", "web-typecheck", "web-build", "verify")]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments
)

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonProjectPath = Join-Path $repositoryRoot "football-predictor"
$webProjectPath = Join-Path $repositoryRoot "web"
$pythonExecutable = Join-Path $pythonProjectPath ".venv\Scripts\python.exe"

function Invoke-ProjectCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$Executable,

        [Parameter()]
        [string[]]$Arguments = @()
    )

    Push-Location $WorkingDirectory
    try {
        & $Executable @Arguments
        $projectCommandExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($projectCommandExitCode -ne 0) {
        exit $projectCommandExitCode
    }
}

if ($Command -in @("test", "train", "api", "verify") -and -not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw "Python environment not found at $pythonExecutable. Create football-predictor/.venv first."
}

switch ($Command) {
    "test" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("-m", "pytest", "-q", "--basetemp", "_tmp/project-entry-pytest") + $CommandArguments)
    }
    "train" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("scripts/run_train.py") + $CommandArguments)
    }
    "api" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("-m", "uvicorn", "api.main:app", "--reload") + $CommandArguments)
    }
    "web-lint" {
        Invoke-ProjectCommand `
            -WorkingDirectory $webProjectPath `
            -Executable "npm" `
            -Arguments (@("run", "lint", "--") + $CommandArguments)
    }
    "web-typecheck" {
        Invoke-ProjectCommand `
            -WorkingDirectory $webProjectPath `
            -Executable "npm" `
            -Arguments (@("run", "typecheck", "--") + $CommandArguments)
    }
    "web-build" {
        Invoke-ProjectCommand `
            -WorkingDirectory $webProjectPath `
            -Executable "npm" `
            -Arguments (@("run", "build", "--") + $CommandArguments)
    }
    "verify" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("-m", "pytest", "-q", "--basetemp", "_tmp/project-entry-pytest")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "lint")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "typecheck")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "build")
    }
}
