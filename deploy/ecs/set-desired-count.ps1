[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(0, 1)]
    [int]$DesiredCount,

    [string]$ClusterName = "upbit-scraper",
    [string]$ServiceName = "upbit-scraper",
    [string]$Region = "ap-northeast-2",
    [string]$Profile = "upbit-admin"
)

$ErrorActionPreference = "Stop"

aws ecs update-service `
    --cluster $ClusterName `
    --service $ServiceName `
    --desired-count $DesiredCount `
    --region $Region `
    --profile $Profile `
    --query "service.{serviceName:serviceName,desiredCount:desiredCount,status:status}" `
    --output table

if ($LASTEXITCODE -ne 0) {
    throw "Failed to set desired count to $DesiredCount."
}
