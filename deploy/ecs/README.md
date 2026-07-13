# ECS Fargate Deployment

This directory contains the deployment templates and PowerShell helpers for
running the Upbit scraper as one long-running ECS Fargate task.

The deployment is intentionally safe by default:

- `TRADING_ENABLED=false`
- `TRADE_ENVIRONMENT=DEMO`
- `ORDER_QUANTITY=0`
- desired count is limited to `0` or `1`
- ECS stops the existing task before starting a replacement
- the task receives no public IP and requires private subnets with outbound access

Do not enable production trading until the production-readiness items in
`spec/vision.md` have been reviewed and implemented.

## Prerequisites

Install and configure AWS CLI v2, Docker Desktop, and an IAM Identity Center
profile. The examples use:

```powershell
$Region = "ap-northeast-2"
$Profile = "upbit-admin"
aws sso login --profile $Profile
```

Create the following AWS networking resources before deploying:

1. A VPC with at least two private subnets.
2. A NAT Gateway in a public subnet, with an Elastic IP.
3. A default route from each selected private subnet to the NAT Gateway.
4. A security group with no inbound rules and outbound access. Allow all
   outbound traffic initially so DNS and the external HTTPS APIs work; tighten
   it only after validating every required destination.

The NAT Gateway Elastic IP is the stable outbound address to allowlist in
Binance. A single NAT Gateway costs less but is not Availability Zone redundant.

## 1. Create the Binance secret

In AWS Secrets Manager, create a secret named `upbit-scraper/binance` with this
JSON structure:

```json
{
  "BINANCE_API_KEY": "your-demo-key",
  "BINANCE_API_SECRET": "your-demo-secret"
}
```

Use the console rather than command-line literals so credentials do not enter
PowerShell history. Record the returned secret ARN.

## 2. Create the ECS task execution role

The script creates or updates the execution role, attaches the standard ECR and
CloudWatch permissions, and grants access only to the supplied secret:

```powershell
$SecretArn = "arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:upbit-scraper/binance-xxxxxx"
$ExecutionRoleArn = .\deploy\ecs\create-execution-role.ps1 `
    -SecretArn $SecretArn `
    -Region $Region `
    -Profile $Profile
```

The application does not currently call AWS APIs, so it does not receive a task
IAM role.

## 3. Test, build, and publish the image

Use an immutable Git SHA or release identifier as the image tag:

```powershell
$ImageTag = git rev-parse --short HEAD
.\deploy\ecs\publish-image.ps1 `
    -ImageTag $ImageTag `
    -Region $Region `
    -Profile $Profile
```

The script runs the unit tests, creates the ECR repository if necessary, builds
the Linux x86-64 image, and pushes it to ECR.

It expects the repository virtual environment and dependencies to exist:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 4. Register a task-definition revision

```powershell
$TaskDefinitionArn = .\deploy\ecs\register-task.ps1 `
    -ImageTag $ImageTag `
    -ExecutionRoleArn $ExecutionRoleArn `
    -SecretArn $SecretArn `
    -Region $Region `
    -Profile $Profile
```

This also creates `/ecs/upbit-scraper` if needed and sets its log retention to
30 days. The checked-in task definition remains a placeholder template; the
rendered version is written only to the system temporary directory and removed
after registration.

## 5. Create or update the ECS service

Supply two private subnet IDs and the task security-group ID:

```powershell
$PrivateSubnets = @("subnet-aaaaaaaa", "subnet-bbbbbbbb")
$TaskSecurityGroup = "sg-cccccccc"

.\deploy\ecs\deploy.ps1 `
    -TaskDefinitionArn $TaskDefinitionArn `
    -PrivateSubnetIds $PrivateSubnets `
    -SecurityGroupId $TaskSecurityGroup `
    -DesiredCount 1 `
    -Region $Region `
    -Profile $Profile
```

The script creates the ECS cluster and service if needed. Existing services are
updated in place. `maximumPercent=100` and `minimumHealthyPercent=0` prevent two
worker tasks from overlapping during a deployment.

## 6. Inspect the worker

```powershell
aws ecs describe-services `
    --cluster upbit-scraper `
    --services upbit-scraper `
    --region $Region `
    --profile $Profile

aws logs tail "/ecs/upbit-scraper" `
    --follow `
    --region $Region `
    --profile $Profile
```

Confirm startup, baseline initialization, repeated Upbit polling, and disabled
trading before making any configuration change.

## Start and stop

Stop the worker:

```powershell
.\deploy\ecs\set-desired-count.ps1 -DesiredCount 0 -Region $Region -Profile $Profile
```

Start the worker:

```powershell
.\deploy\ecs\set-desired-count.ps1 -DesiredCount 1 -Region $Region -Profile $Profile
```

Scaling to zero stops Fargate task compute charges. NAT Gateway, Elastic IP,
Secrets Manager, ECR, and CloudWatch storage charges continue.

## Deploy an update

Publish a new immutable image tag, register another task-definition revision,
and run `deploy.ps1` with the new task-definition ARN. The ECS deployment circuit
breaker is enabled and rolls back repeated startup failures when a previously
completed deployment is available.

## Security and production notes

- Never put credentials into this directory or the task definition.
- Keep Binance withdrawal permission disabled.
- Restrict the execution-role secret permission to the exact secret ARN.
- Keep the task security group free of inbound rules.
- Retain one service task; do not enable ECS Service Auto Scaling.
- The current Dockerfile runs as root. Add a non-root image user and then enable
  `readonlyRootFilesystem` and a numeric `user` in `task-definition.json` before
  production.
- Secret changes require a new task. Register/deploy again or force a new ECS
  service deployment after rotating credentials.
