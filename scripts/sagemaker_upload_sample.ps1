param(
    [Parameter(Mandatory=$true)][string]$Bucket,
    [string]$Profile = "",
    [string]$Region = "us-east-1"
)
$ErrorActionPreference = "Stop"
$profileArgs = @()
if ($Profile) { $profileArgs = @("--profile", $Profile) }
$caller = aws @profileArgs sts get-caller-identity --output json | ConvertFrom-Json
if ($caller.Arn -like "*:root") { throw "Refusing to upload with AWS root credentials." }
.venv\Scripts\python.exe scripts\make_sagemaker_sample_inputs.py --replace
$root = "s3://$Bucket/entity-resolution"
aws @profileArgs s3 sync tmp/sagemaker-sample/features/feat_v2_0 "$root/features/feat_v2_0" --region $Region --only-show-errors
aws @profileArgs s3 sync tmp/sagemaker-sample/candidates/candidate_v1 "$root/candidates/candidate_v1" --region $Region --only-show-errors
aws @profileArgs s3 sync tmp/sagemaker-sample/candidate-metrics/candidate_v1 "$root/candidate-metrics/candidate_v1" --region $Region --only-show-errors
aws @profileArgs s3 sync tmp/sagemaker-sample/labels/fold_v1 "$root/labels/fold_v1" --region $Region --only-show-errors
Write-Output "Uploaded deterministic sample inputs below $root"
