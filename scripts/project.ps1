[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("test", "train", "api", "python-lint", "python-typecheck", "web-lint", "web-typecheck", "web-build", "verify")]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments
)

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonProjectPath = Join-Path $repositoryRoot "football-predictor"
$webProjectPath = Join-Path $repositoryRoot "web"
$pythonExecutable = Join-Path $pythonProjectPath ".venv\Scripts\python.exe"
$projectCommandArguments = @($CommandArguments | Where-Object { $_ })
$pythonLintTargets = @("src/api/routes", "src/api/services", "tests/test_chat_routes.py", "tests/test_chat_http_integration.py", "tests/test_operations_routes.py", "tests/test_research_copilot_service.py")
$pythonTypecheckTargets = @("src/api/services/chat_client.py", "src/api/routes/operations.py")

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

if ($Command -in @("test", "train", "api", "python-lint", "python-typecheck", "verify") -and -not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw "Python environment not found at $pythonExecutable. Create football-predictor/.venv first."
}

switch ($Command) {
    "test" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("-m", "pytest", "-q", "--basetemp", "_tmp/project-entry-pytest") + $projectCommandArguments)
    }
    "train" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("scripts/run_train.py") + $projectCommandArguments)
    }
    "api" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("-m", "uvicorn", "api.main:app", "--reload") + $projectCommandArguments)
    }
    "python-lint" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("-m", "ruff", "check") + $pythonLintTargets + $projectCommandArguments)
    }
    "python-typecheck" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("-m", "mypy", "--explicit-package-bases") + $pythonTypecheckTargets + $projectCommandArguments)
    }
    "web-lint" {
        Invoke-ProjectCommand `
            -WorkingDirectory $webProjectPath `
            -Executable "npm" `
            -Arguments (@("run", "lint", "--") + $projectCommandArguments)
    }
    "web-typecheck" {
        Invoke-ProjectCommand `
            -WorkingDirectory $webProjectPath `
            -Executable "npm" `
            -Arguments (@("run", "typecheck", "--") + $projectCommandArguments)
    }
    "web-build" {
        Invoke-ProjectCommand `
            -WorkingDirectory $webProjectPath `
            -Executable "npm" `
            -Arguments (@("run", "build", "--") + $projectCommandArguments)
    }
    "verify" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("-m", "ruff", "check") + $pythonLintTargets)
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("-m", "mypy", "--explicit-package-bases") + $pythonTypecheckTargets)
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("-m", "pytest", "-q", "--basetemp", "_tmp/project-entry-pytest")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "lint")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "typecheck")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "build")
    }
}
