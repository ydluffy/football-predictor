[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("test", "train", "api", "data-model-quality", "python-lock", "python-lock-check", "python-lint", "python-typecheck", "secret-scan", "dependency-audit", "security", "web-lint", "web-typecheck", "web-build", "verify")]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments
)

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonProjectPath = Join-Path $repositoryRoot "football-predictor"
$webProjectPath = Join-Path $repositoryRoot "web"
$pythonExecutable = Join-Path $pythonProjectPath ".venv\Scripts\python.exe"
$projectCommandArguments = @($CommandArguments | Where-Object { $_ })
$pythonLintTargets = @("src/api/observability.py", "src/api/routes", "src/api/services", "src/quality", "scripts/check_data_model_quality.py", "scripts/check_dependency_lock.py", "scripts/check_secrets.py", "tests/test_chat_routes.py", "tests/test_chat_http_integration.py", "tests/test_data_model_quality_gate.py", "tests/test_observability.py", "tests/test_operations_routes.py", "tests/test_research_copilot_service.py")
$pythonTypecheckTargets = @("src/api/observability.py", "src/api/services/chat_client.py", "src/api/routes/operations.py", "src/quality/data_model_gate.py", "scripts/check_data_model_quality.py", "scripts/check_dependency_lock.py", "scripts/check_secrets.py")

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

if ($Command -in @("test", "train", "api", "data-model-quality", "python-lock", "python-lock-check", "python-lint", "python-typecheck", "secret-scan", "dependency-audit", "security", "verify") -and -not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
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
    "data-model-quality" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments (@("scripts/check_data_model_quality.py") + $projectCommandArguments)
    }
    "python-lock" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("-m", "piptools", "compile", "--upgrade", "--extra", "dev", "--resolver", "backtracking", "--strip-extras", "--allow-unsafe", "--no-emit-index-url", "--no-emit-trusted-host", "--output-file", "requirements.txt", "pyproject.toml")
    }
    "python-lock-check" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("scripts/check_dependency_lock.py")
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
    "secret-scan" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("scripts/check_secrets.py")
    }
    "dependency-audit" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("scripts/check_dependency_lock.py")
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("-m", "pip_audit", "--requirement", "requirements.txt", "--no-deps", "--disable-pip", "--progress-spinner", "off")
    }
    "security" {
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("scripts/check_dependency_lock.py")
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("scripts/check_secrets.py")
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("-m", "pip_audit", "--requirement", "requirements.txt", "--no-deps", "--disable-pip", "--progress-spinner", "off")
        Invoke-ProjectCommand `
            -WorkingDirectory $webProjectPath `
            -Executable "npm" `
            -Arguments @("audit", "--audit-level=high")
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
            -Arguments @("scripts/check_dependency_lock.py")
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("scripts/check_secrets.py")
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
            -Arguments @("scripts/check_data_model_quality.py", "--dataset", "tests/fixtures/data_model_quality/current.csv", "--reference", "tests/fixtures/data_model_quality/reference.csv", "--metrics", "tests/fixtures/data_model_quality/metrics.json", "--as-of", "2026-08-27T00:00:00Z", "--output", "_tmp/verify-data-model-quality.json")
        Invoke-ProjectCommand `
            -WorkingDirectory $pythonProjectPath `
            -Executable $pythonExecutable `
            -Arguments @("-m", "pytest", "-q", "--basetemp", "_tmp/project-entry-pytest")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "lint")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "typecheck")
        Invoke-ProjectCommand -WorkingDirectory $webProjectPath -Executable "npm" -Arguments @("run", "build")
    }
}
