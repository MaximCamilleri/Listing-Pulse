[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskDefinitionArn,

    [Parameter(Mandatory = $true)]
    [string[]]$PrivateSubnetIds,

    [Parameter(Mandatory = $true)]
    [string]$SecurityGroupId,

    [ValidateRange(0, 1)]
    [int]$DesiredCount = 1,
    [string]$ClusterName = "upbit-scraper",
    [string]$ServiceName = "upbit-scraper",
    [string]$Region = "ap-northeast-2",
    [string]$Profile = "upbit-admin"
)

$ErrorActionPreference = "Stop"
$RequestPath = Join-Path ([System.IO.Path]::GetTempPath()) "upbit-scraper-ecs-service.json"

try {
    $clusters = aws ecs describe-clusters `
        --clusters $ClusterName `
        --region $Region `
        --profile $Profile `
        --output json | ConvertFrom-Json

    $activeCluster = $clusters.clusters | Where-Object { $_.status -eq "ACTIVE" }
    if (-not $activeCluster) {
        aws ecs create-cluster `
            --cluster-name $ClusterName `
            --tags "key=Project,value=upbit-scraper" "key=Environment,value=demo" `
            --region $Region `
            --profile $Profile `
            --output json | Out-Null

        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create ECS cluster '$ClusterName'."
        }
    }

    $serviceResponse = aws ecs describe-services `
        --cluster $ClusterName `
        --services $ServiceName `
        --region $Region `
        --profile $Profile `
        --output json | ConvertFrom-Json

    $existingService = $serviceResponse.services | Where-Object { $_.status -ne "INACTIVE" }
    $deploymentConfiguration = @{
        maximumPercent = 100
        minimumHealthyPercent = 0
        deploymentCircuitBreaker = @{
            enable = $true
            rollback = $true
        }
    }
    $networkConfiguration = @{
        awsvpcConfiguration = @{
            subnets = @($PrivateSubnetIds)
            securityGroups = @($SecurityGroupId)
            assignPublicIp = "DISABLED"
        }
    }

    if ($existingService) {
        $request = @{
            cluster = $ClusterName
            service = $ServiceName
            taskDefinition = $TaskDefinitionArn
            desiredCount = $DesiredCount
            platformVersion = "LATEST"
            deploymentConfiguration = $deploymentConfiguration
            networkConfiguration = $networkConfiguration
            forceNewDeployment = $true
        }
        $operation = "update-service"
    }
    else {
        $request = @{
            cluster = $ClusterName
            serviceName = $ServiceName
            taskDefinition = $TaskDefinitionArn
            desiredCount = $DesiredCount
            launchType = "FARGATE"
            platformVersion = "LATEST"
            deploymentConfiguration = $deploymentConfiguration
            networkConfiguration = $networkConfiguration
            enableECSManagedTags = $true
            propagateTags = "TASK_DEFINITION"
            tags = @(
                @{ key = "Project"; value = "upbit-scraper" },
                @{ key = "Environment"; value = "demo" }
            )
        }
        $operation = "create-service"
    }

    $requestJson = $request | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($RequestPath, $requestJson)
    aws ecs $operation `
        --cli-input-json "file://$RequestPath" `
        --region $Region `
        --profile $Profile `
        --query "service.serviceArn" `
        --output text

    if ($LASTEXITCODE -ne 0) {
        throw "ECS service operation '$operation' failed."
    }

    aws ecs wait services-stable `
        --cluster $ClusterName `
        --services $ServiceName `
        --region $Region `
        --profile $Profile

    if ($LASTEXITCODE -ne 0) {
        throw "ECS service did not reach a stable state. Inspect its service events and stopped tasks."
    }
}
finally {
    Remove-Item -LiteralPath $RequestPath -Force -ErrorAction SilentlyContinue
}
