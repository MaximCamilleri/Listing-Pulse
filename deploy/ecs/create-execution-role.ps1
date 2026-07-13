[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SecretArn,

    [string]$RoleName = "upbit-scraper-execution-role",
    [string]$Region = "ap-northeast-2",
    [string]$Profile = "upbit-admin"
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$TrustPolicyPath = Join-Path $ScriptDirectory "execution-role-trust-policy.json"
$PermissionsTemplatePath = Join-Path $ScriptDirectory "execution-role-policy.json"
$RenderedPolicyPath = Join-Path ([System.IO.Path]::GetTempPath()) "upbit-scraper-execution-role-policy.json"

try {
    $role = aws iam get-role `
        --role-name $RoleName `
        --profile $Profile `
        --output json 2>$null | ConvertFrom-Json

    if ($LASTEXITCODE -ne 0 -or $null -eq $role.Role.Arn) {
        aws iam create-role `
            --role-name $RoleName `
            --assume-role-policy-document "file://$TrustPolicyPath" `
            --profile $Profile `
            --output json | Out-Null

        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create IAM role '$RoleName'."
        }
    }

    aws iam attach-role-policy `
        --role-name $RoleName `
        --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" `
        --profile $Profile

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to attach AmazonECSTaskExecutionRolePolicy to '$RoleName'."
    }

    $renderedPolicy = (Get-Content $PermissionsTemplatePath -Raw).Replace("__SECRET_ARN__", $SecretArn)
    $renderedPolicy | ConvertFrom-Json | Out-Null
    [System.IO.File]::WriteAllText($RenderedPolicyPath, $renderedPolicy)

    aws iam put-role-policy `
        --role-name $RoleName `
        --policy-name "ReadUpbitScraperBinanceSecret" `
        --policy-document "file://$RenderedPolicyPath" `
        --profile $Profile

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to attach the Secrets Manager policy to '$RoleName'."
    }

    aws iam get-role `
        --role-name $RoleName `
        --query "Role.Arn" `
        --output text `
        --profile $Profile
}
finally {
    Remove-Item -LiteralPath $RenderedPolicyPath -Force -ErrorAction SilentlyContinue
}
