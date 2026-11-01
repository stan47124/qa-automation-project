# Import only; no Jenkins operation runs until Enable-JenkinsScmPolling is called.
# XML 1.1 is handled by the installed JDK without changing its version to 1.0.
# The engine retains -http and only .jenkins-cli\codex-ci-auth.txt (never auth.txt).
$script:JenkinsPollingCiDirectory = $PSScriptRoot

function Enable-JenkinsScmPolling {
    [CmdletBinding()]
    param(
        [switch]$VerifyOnly,
        [string]$BackupDirectory = (Join-Path $env:USERPROFILE '.jenkins-cli')
    )

    $ErrorActionPreference = 'Stop'
    $ciDirectory = $script:JenkinsPollingCiDirectory
    if ([string]::IsNullOrWhiteSpace($ciDirectory)) {
        throw 'Import the script from the repository, or use the documented Python command.'
    }
    $python = Join-Path (Split-Path $ciDirectory -Parent) '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project .venv Python is unavailable.' }
    $arguments = @((Join-Path $ciDirectory 'jenkins_polling.py'))
    if ($VerifyOnly) { $arguments += '--verify-only' }
    else { $arguments += @('--backup-directory', $BackupDirectory) }

    $ErrorActionPreference = 'Continue'
    $output = & $python @arguments 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $output) { Write-Output ($line.ToString()) }
    if ($code -ne 0) { throw 'Polling operation failed. See the sanitized diagnostic above; no raw XML is printed.' }
}
