[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ImageTag,

    [string]$RepositoryName = "upbit-scraper",
    [string]$Region = "ap-northeast-2",
    [string]$Profile = "upbit-admin",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$PythonExecutable = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$AccountId = aws sts get-caller-identity `
    --query "Account" `
    --output text `
    --profile $Profile

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($AccountId)) {
    throw "Unable to determine the AWS account ID. Run 'aws sso login --profile $Profile'."
}

$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$RemoteImage = "$Registry/${RepositoryName}:$ImageTag"

$repository = aws ecr describe-repositories `
    --repository-names $RepositoryName `
    --region $Region `
    --profile $Profile `
    --output json 2>$null | ConvertFrom-Json

if ($LASTEXITCODE -ne 0 -or $null -eq $repository.repositories) {
    aws ecr create-repository `
        --repository-name $RepositoryName `
        --image-scanning-configuration scanOnPush=true `
        --region $Region `
        --profile $Profile `
        --output json | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create ECR repository '$RepositoryName'."
    }
}

if (-not $SkipTests) {
    if (-not (Test-Path -LiteralPath $PythonExecutable)) {
        throw "Python virtual environment not found. Create .venv and install requirements before publishing."
    }

    & $PythonExecutable `
        -m unittest discover -s tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) {
        throw "Repository tests failed. The image was not published."
    }
}

aws ecr get-login-password --region $Region --profile $Profile |
    docker login --username AWS --password-stdin $Registry
if ($LASTEXITCODE -ne 0) {
    throw "Docker authentication to ECR failed."
}

docker build --platform linux/amd64 -t "${RepositoryName}:$ImageTag" $RepositoryRoot
if ($LASTEXITCODE -ne 0) {
    throw "Docker build failed."
}

docker tag "${RepositoryName}:$ImageTag" $RemoteImage
docker push $RemoteImage
if ($LASTEXITCODE -ne 0) {
    throw "Docker push failed."
}

$RemoteImage
