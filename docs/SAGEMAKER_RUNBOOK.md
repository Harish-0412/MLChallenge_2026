# SageMaker Phase 3 runbook

This runbook takes the tested local job contracts to one bounded SageMaker sample execution. It deliberately separates read-only
validation from AWS mutations. No endpoint is created; every workload is a Processing or Training job.

## 0. Current safety blocker

The currently configured shared AWS credentials authenticate as the account root user. Do not use them for this project. Before any
upload, image push, pipeline upsert, or execution:

1. Enable MFA on the root user.
2. Remove/deactivate root access keys after establishing an alternative.
3. Prefer IAM Identity Center or an assumable deployment role with temporary credentials.
4. Configure a named AWS CLI profile and confirm that `aws --profile <name> sts get-caller-identity` returns an assumed role/user ARN,
   never an ARN ending in `:root`.

The repository's mutating scripts and CLI reject a root caller.

## 1. Create project resources

In `us-east-1`, create:

- One private S3 bucket; block all public access, enable versioning and default encryption. A customer-managed KMS key is optional.
- Private ECR repositories `entity-resolution-cpu` and `entity-resolution-neural`, with scan-on-push enabled.
- The execution role `SageMakerEntityResolutionExecution` using
  `cloud/sagemaker/iam/execution-role-trust.json` and the scoped policy template in the same folder.
- A deployment identity/role using the deployment policy template. Replace `REPLACE_ACCOUNT_ID` and `REPLACE_BUCKET` first.

The execution role policy is intentionally scoped to the project bucket prefix and two ECR repositories. Add KMS permissions only if
`kms_key_arn` is configured.

## 2. Create budget protection

In AWS Budgets create a monthly cost budget no higher than **USD 160**, preserving USD 40 from the USD 200 envelope as contingency.
Add actual-cost alerts at 50%, 75%, 90%, and 100%. Treat the repository ledger as the per-job planning record; AWS Budgets remains the
account-side backstop. Verify how promotional credits are represented in the chosen budget filters.

## 3. Configure locally

```powershell
Copy-Item configs\sagemaker.sample.json configs\sagemaker.json
```

Replace the bucket, execution-role ARN, and image URIs. Keep the region `us-east-1`. If no customer KMS key is used, leave
`kms_key_arn` empty. The instance prices in the file are conservative planning estimates, not a price quotation; verify them in the
AWS console for the region before a full run.

Install the pinned authoring environment:

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements-sagemaker.txt
```

## 4. Verify job contracts locally

```powershell
.venv\Scripts\python.exe scripts\run_sagemaker_local_smoke.py
.venv\Scripts\python.exe -W ignore -m unittest discover -s tests -p test_sagemaker_foundation.py -v
```

The smoke must end with `LOCAL_SAGEMAKER_SMOKE_PASS`. It uses synthetic data and makes no AWS calls.

## 5. Build and push immutable images

Obtain a `us-east-1` AWS PyTorch GPU training DLC URI compatible with the pinned neural dependencies. Then run with the non-root
profile active:

```powershell
.\scripts\sagemaker_build_images.ps1 `
  -AccountId <account-id> `
  -NeuralBaseImage <pytorch-dlc-uri> `
  -Tag phase3-v1 `
  -Profile <profile>
```

Record the resulting immutable image digest. Prefer replacing the mutable tag in `configs/sagemaker.json` with a digest URI.

## 6. Upload deterministic sample inputs

```powershell
.\scripts\sagemaker_upload_sample.ps1 -Bucket <bucket> -Profile <profile>
```

Expected prefixes:

```text
s3://<bucket>/entity-resolution/
  features/feat_v2_0/
  candidates/candidate_v1/{train,early-stop,calibration,holdout,test}/
  candidate-metrics/candidate_v1/
  labels/fold_v1/{calibration,holdout,test}/
  pipeline-executions/<execution-id>/...
```

## 7. Validate and render without spending compute

```powershell
.venv\Scripts\python.exe -m cloud.sagemaker.cli --config configs/sagemaker.json validate --mode sample
.venv\Scripts\python.exe -m cloud.sagemaker.cli --config configs/sagemaker.json render --mode sample --output tmp\sagemaker-pipeline-sample.json
```

Inspect the rendered definition. It must contain candidate and model quality gates, maximum runtimes, encrypted volumes/outputs when a
KMS key is configured, versioned execution prefixes, and no endpoint step.

## 8. Upsert and start one sample execution

Upsert is an AWS mutation but does not launch training compute:

```powershell
.venv\Scripts\python.exe -m cloud.sagemaker.cli --config configs/sagemaker.json upsert --mode sample --confirm UPSERT-SAMPLE
```

Create `tmp/sample-parameters.json` with a unique `ExperimentId` and any S3 overrides, then start the billable run:

```powershell
.venv\Scripts\python.exe -m cloud.sagemaker.cli --config configs/sagemaker.json start --mode sample `
  --parameters tmp\sample-parameters.json --confirm START-SAMPLE
```

Never start a second run until the first finishes and its actual cost/runtime is entered in
`reports/modeling/aws_budget_ledger.json`. Stop a runaway execution with `aws sagemaker stop-pipeline-execution`.

## 9. Quality gates and promotion

The sample pipeline fails closed unless:

- candidate recall is at least 0.99;
- candidate oracle macro-F0.5 is at least 0.97;
- holdout model macro-F0.5 is at least 0.85;
- singleton false-positive rate is at most 0.03.

The target remains 0.95 macro-F0.5. A passing 0.85 sample does not authorize a full run automatically. Promote to `full` only after
updating actual costs, replacing synthetic inputs with frozen Member B artifacts, checking available G5/R5 capacity, and reviewing the
rendered full pipeline definition.
