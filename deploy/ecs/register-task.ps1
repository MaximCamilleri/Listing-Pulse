[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ImageTag,

    [Parameter(Mandatory = $true)]
    [string]$ExecutionRoleArn,

    [Parameter(Mandatory = $true)]
    [string]$SecretArn,

    [string]$RepositoryName = "upbit-scraper",
    [string]$LogGroupName = "/ecs/upbit-scraper",
    [int]$LogRetentionDays = 30,
    [string]$Region = "ap-northeast-2",
    [string]$Profile = "upbit-admin"
)

$ErrorActionPreference = "Stop"
$TemplatePath = Join-Path $PSScriptRoot "task-definition.json"
$RenderedTaskPath = Join-Path ([System.IO.Path]::GetTempPath()) "upbit-scraper-task-definition.json"
$AccountId = aws sts get-caller-identity `
    --query "Account" `
    --output text `
    --profile $Profile

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($AccountId)) {
    throw "Unable to determine the AWS account ID. Run 'aws sso login --profile $Profile'."
}

try {
    $logGroups = aws logs describe-log-groups `
        --log-group-name-prefix $LogGroupName `
        --region $Region `
        --profile $Profile `
        --output json | ConvertFrom-Json

    $logGroupExists = $logGroups.logGroups | Where-Object { $_.logGroupName -eq $LogGroupName }
    if (-not $logGroupExists) {
        aws logs create-log-group `
            --log-group-name $LogGroupName `
            --region $Region `
            --profile $Profile
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create CloudWatch log group '$LogGroupName'."
        }
    }

    aws logs put-retention-policy `
        --log-group-name $LogGroupName `
        --retention-in-days $LogRetentionDays `
        --region $Region `
        --profile $Profile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set retention on CloudWatch log group '$LogGroupName'."
    }

    $renderedTask = Get-Content $TemplatePath -Raw
    $replacements = @{
        "__AWS_ACCOUNT_ID__" = $AccountId
        "__AWS_REGION__" = $Region
        "__REPOSITORY_NAME__" = $RepositoryName
        "__IMAGE_TAG__" = $ImageTag
        "__EXECUTION_ROLE_ARN__" = $ExecutionRoleArn
        "__SECRET_ARN__" = $SecretArn
        "__LOG_GROUP_NAME__" = $LogGroupName
    }

    foreach ($replacement in $replacements.GetEnumerator()) {
        $renderedTask = $renderedTask.Replace($replacement.Key, $replacement.Value)
    }

    $renderedTask | ConvertFrom-Json | Out-Null
    [System.IO.File]::WriteAllText($RenderedTaskPath, $renderedTask)

    aws ecs register-task-definition `
        --cli-input-json "file://$RenderedTaskPath" `
        --region $Region `
        --profile $Profile `
        --query "taskDefinition.taskDefinitionArn" `
        --output text

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to register the ECS task definition."
    }
}
finally {
    Remove-Item -LiteralPath $RenderedTaskPath -Force -ErrorAction SilentlyContinue
}
