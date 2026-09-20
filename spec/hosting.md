# Hosting

## ARM64 Decision

The worker targets Linux ARM64 (`linux/arm64`) for deployment on AWS Graviton through ECS Fargate. Published images contain only the ARM64 variant.

The image publishing workflow and pull-request test workflow use native `ubuntu-24.04-arm` GitHub Actions runners. The Docker build explicitly targets `linux/arm64`. The existing `python:3.13-slim` base image supports ARM64.

Images are pushed to Amazon ECR with the Git commit SHA as their tag. Publishing an image does not update the ECS service.

## ECS Deployment Requirements

Before deploying an ARM64 image, register a task definition using the following runtime platform and update the service to that task definition:

```json
"runtimePlatform": {
  "cpuArchitecture": "ARM64",
  "operatingSystemFamily": "LINUX"
}
```

Use Fargate Linux platform version `1.4.0` or later in a region and availability zone that support ARM64. The ECS task definition and service configuration are managed outside this repository.
