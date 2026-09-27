param(
    [Parameter(Mandatory=$true)][string]$AccountId,
    [string]$Region = "us-east-1",
    [string]$Tag = "phase3-v1",
    [string]$NeuralBaseImage = "",
    [switch]$CpuOnly,
    [string]$Profile = ""
)
$ErrorActionPreference = "Stop"
$profileArgs = @()
if ($Profile) { $profileArgs = @("--profile", $Profile) }
$caller = aws @profileArgs sts get-caller-identity --output json | ConvertFrom-Json
if ($caller.Arn -like "*:root") { throw "Refusing to push images with AWS root credentials." }
$registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
aws @profileArgs ecr describe-repositories --region $Region --repository-names entity-resolution-cpu entity-resolution-neural | Out-Null
aws @profileArgs ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
docker build -f cloud/sagemaker/docker/cpu.Dockerfile -t "entity-resolution-cpu:$Tag" .
docker tag "entity-resolution-cpu:$Tag" "$registry/entity-resolution-cpu:$Tag"
docker push "$registry/entity-resolution-cpu:$Tag"
Write-Output "$registry/entity-resolution-cpu:$Tag"
if ($CpuOnly) { exit 0 }
if (-not $NeuralBaseImage) { throw "-NeuralBaseImage is required unless -CpuOnly is set." }
docker build --build-arg "BASE_IMAGE=$NeuralBaseImage" -f cloud/sagemaker/docker/neural.Dockerfile -t "entity-resolution-neural:$Tag" .
docker tag "entity-resolution-neural:$Tag" "$registry/entity-resolution-neural:$Tag"
docker push "$registry/entity-resolution-neural:$Tag"
Write-Output "$registry/entity-resolution-neural:$Tag"
