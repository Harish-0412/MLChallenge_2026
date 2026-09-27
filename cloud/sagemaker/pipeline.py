"""SageMaker Pipeline v3 definition. Building the definition is read-only."""
from __future__ import annotations

import boto3
from contextlib import nullcontext
import json
from unittest.mock import patch

from sagemaker.core.helper.session_helper import Session
from sagemaker.core.network import NetworkConfig
from sagemaker.core.processing import Processor
from sagemaker.core.shapes import (
    CheckpointConfig, OutputDataConfig, ProcessingInput, ProcessingOutput,
    ProcessingS3Input, ProcessingS3Output, StoppingCondition, Tag,
)
from sagemaker.core.training.configs import Compute, InputData, MetricDefinition, Networking
from sagemaker.core.workflow.conditions import ConditionGreaterThanOrEqualTo, ConditionLessThanOrEqualTo
from sagemaker.core.workflow.execution_variables import ExecutionVariables
from sagemaker.core.workflow.functions import Join, JsonGet
from sagemaker.core.workflow.parameters import ParameterFloat, ParameterInteger, ParameterString
from sagemaker.core.workflow.pipeline_context import PipelineSession
from sagemaker.core.workflow.properties import PropertyFile
from sagemaker.mlops.workflow.condition_step import ConditionStep
from sagemaker.mlops.workflow.fail_step import FailStep
from sagemaker.mlops.workflow.pipeline import Pipeline
from sagemaker.mlops.workflow.steps import CacheConfig, ProcessingStep, TrainingStep
from sagemaker.train import ModelTrainer

from .foundation import S3Layout
from .metrics import TRAINING_METRIC_DEFINITIONS


def _normalize_tag_members(node):
    """Work around SDK v3 serializing ModelTrainer Tag fields as key/value."""
    if isinstance(node, dict):
        normalized = {key: _normalize_tag_members(value) for key, value in node.items()}
        tags = normalized.get("Tags")
        if isinstance(tags, list):
            normalized["Tags"] = [
                {"Key": item["key"], "Value": item["value"]}
                if isinstance(item, dict) and set(item) == {"key", "value"}
                else item
                for item in tags
            ]
        return normalized
    if isinstance(node, list):
        return [_normalize_tag_members(item) for item in node]
    return node


class SchemaCompatiblePipeline(Pipeline):
    def definition(self) -> str:
        return json.dumps(_normalize_tag_members(json.loads(super().definition())))


def _s3_input(name, uri, local_path):
    return ProcessingInput(
        input_name=name,
        s3_input=ProcessingS3Input(
            s3_uri=uri, s3_data_type="S3Prefix", local_path=local_path,
            s3_input_mode="File", s3_data_distribution_type="FullyReplicated",
        ),
    )


def _s3_output(name, uri, local_path):
    return ProcessingOutput(
        output_name=name,
        s3_output=ProcessingS3Output(s3_uri=uri, s3_upload_mode="EndOfJob", local_path=local_path),
    )


def build_pipeline(config: dict, *, mode: str = "sample", offline: bool = False,
                   profile_name: str | None = None) -> Pipeline:
    if mode not in ("sample", "full"):
        raise ValueError("mode must be sample or full")
    resources = config["resources"][mode]
    layout = S3Layout(config["bucket"], config["project"])
    pipeline_name = f"entity-resolution-{mode}"
    boto_session = boto3.Session(profile_name=profile_name, region_name=config["region"])
    sdk_session = Session(boto_session=boto_session, default_bucket=config["bucket"])
    session = PipelineSession(boto_session=boto_session, sagemaker_client=sdk_session.sagemaker_client,
                              default_bucket=config["bucket"])

    feature_uri = ParameterString("FeatureS3Uri", default_value=layout.versioned("features", "feat_v2_0"))
    candidate_uri = ParameterString("CandidateS3Uri", default_value=layout.versioned("candidates", "candidate_v1"))
    candidate_metrics_uri = ParameterString("CandidateMetricsS3Uri", default_value=layout.versioned("candidate-metrics", "candidate_v1"))
    labels_uri = ParameterString("LabelsS3Uri", default_value=layout.versioned("labels", "fold_v1"))
    experiment_id = ParameterString("ExperimentId", default_value=f"{mode}-manual")
    processing_instance = ParameterString("ProcessingInstanceType", default_value=resources["processing_instance"])
    training_instance = ParameterString("TrainingInstanceType", default_value=resources["training_instance"])
    processing_timeout = ParameterInteger("ProcessingMaxSeconds", default_value=resources["processing_max_seconds"])
    training_timeout = ParameterInteger("TrainingMaxSeconds", default_value=resources["training_max_seconds"])
    volume_gb = ParameterInteger("VolumeSizeGb", default_value=resources["volume_gb"])
    min_recall = ParameterFloat("MinimumCandidateRecall", default_value=config["quality_gates"]["minimum_candidate_recall"])
    min_oracle = ParameterFloat("MinimumCandidateOracleF05", default_value=config["quality_gates"]["minimum_candidate_oracle_f05"])
    min_model = ParameterFloat("MinimumModelMacroF05", default_value=config["quality_gates"]["minimum_model_macro_f05"])
    max_singleton_fp = ParameterFloat("MaximumSingletonFalsePositiveRate", default_value=config["quality_gates"]["maximum_singleton_false_positive_rate"])
    parameters = [feature_uri, candidate_uri, candidate_metrics_uri, labels_uri, experiment_id,
                  processing_instance, training_instance, processing_timeout, training_timeout, volume_gb,
                  min_recall, min_oracle, min_model, max_singleton_fp]

    run_root = Join(on="/", values=[layout.root, "pipeline-executions", ExecutionVariables.PIPELINE_EXECUTION_ID])
    tags = [{"Key": key, "Value": value} for key, value in config["tags"].items()]
    model_tags = [Tag(key=key, value=value) for key, value in config["tags"].items()]
    kms = config.get("kms_key_arn") or None
    processing_network = NetworkConfig(enable_network_isolation=False, encrypt_inter_container_traffic=True)
    training_network = Networking(enable_network_isolation=True, enable_inter_container_traffic_encryption=True)
    cache = CacheConfig(enable_caching=True, expire_after="30d")
    processing_common = dict(
        role=config["role_arn"], image_uri=config["images"]["cpu"], instance_count=1,
        instance_type=processing_instance, volume_size_in_gb=volume_gb,
        output_kms_key=kms, volume_kms_key=kms, max_runtime_in_seconds=processing_timeout,
        sagemaker_session=session, tags=tags, network_config=processing_network,
        env={
            "EMIT_CLOUDWATCH": "1",
            "CLOUDWATCH_NAMESPACE": "MLChallenge/EntityResolution",
            # Processing containers do not consistently receive a default
            # region variable. boto3 needs this to resolve the CloudWatch
            # endpoint used by the job-side metric emitter.
            "AWS_DEFAULT_REGION": config["region"],
        },
    )

    quality_processor = Processor(entrypoint=["python", "/opt/program/cloud/sagemaker/jobs/candidate_quality.py"],
                                  base_job_name="entity-resolution-candidate-quality", **processing_common)
    quality_args = quality_processor.run(
        inputs=[_s3_input("candidate-metrics", candidate_metrics_uri, "/opt/ml/processing/input/candidate-metrics")],
        outputs=[_s3_output("quality", Join(on="/", values=[run_root, "candidate-quality"]), "/opt/ml/processing/output/quality")],
        arguments=["--experiment-id", experiment_id], wait=False,
    )
    quality_file = PropertyFile(name="CandidateQuality", output_name="quality", path="quality.json")
    quality_step = ProcessingStep("CandidateQuality", step_args=quality_args, property_files=[quality_file], cache_config=cache)

    pair_processor = Processor(entrypoint=["python", "/opt/program/cloud/sagemaker/jobs/build_pair_sets.py"],
                               base_job_name="entity-resolution-build-pairs", **processing_common)
    pair_args = pair_processor.run(
        inputs=[_s3_input("features", feature_uri, "/opt/ml/processing/input/features"),
                _s3_input("candidates", candidate_uri, "/opt/ml/processing/input/candidates")],
        outputs=[_s3_output("pairs", Join(on="/", values=[run_root, "pairs"]), "/opt/ml/processing/output/pairs")],
        arguments=["--mode", mode, "--experiment-id", experiment_id], wait=False,
    )
    pair_step = ProcessingStep("BuildPairSets", step_args=pair_args, cache_config=cache)
    pair_root = pair_step.properties.ProcessingOutputConfig.Outputs["pairs"].S3Output.S3Uri

    output_kwargs = {"s3_output_path": Join(on="/", values=[run_root, "models"])}
    if kms:
        output_kwargs["kms_key_id"] = kms
    # SDK v3 validates IAM roles while constructing ModelTrainer. Offline rendering
    # bypasses only that read-only lookup; mutating CLI commands never set offline.
    role_context = (
        patch("sagemaker.train.defaults.resolve_and_validate_role", side_effect=lambda provided_role, **_: provided_role)
        if offline else nullcontext()
    )
    with role_context:
        trainer = ModelTrainer(
            role=config["role_arn"], training_image=config["images"]["cpu"], base_job_name="entity-resolution-gbdt",
            sagemaker_session=session,
            compute=Compute(instance_type=training_instance, instance_count=1, volume_size_in_gb=resources["volume_gb"],
                            volume_kms_key_id=kms, enable_managed_spot_training=False),
            networking=training_network,
            stopping_condition=StoppingCondition(max_runtime_in_seconds=resources["training_max_seconds"]),
            output_data_config=OutputDataConfig(**output_kwargs),
            checkpoint_config=CheckpointConfig(s3_uri=Join(on="/", values=[run_root, "checkpoints", "gbdt"]),
                                               local_path="/opt/ml/checkpoints"),
            hyperparameters={"backend": "xgboost", "seed": "20260926", "n_estimators": "500", "max_depth": "5",
                             "learning_rate": "0.05", "experiment_id": experiment_id},
            tags=model_tags,
        ).with_metric_definitions([MetricDefinition(name=item["name"], regex=item["regex"])
                                   for item in TRAINING_METRIC_DEFINITIONS])
    train_args = trainer.train(input_data_config=[
        InputData(channel_name="train", data_source=Join(on="/", values=[pair_root, "train"]), content_type="application/x-parquet"),
        InputData(channel_name="early-stop", data_source=Join(on="/", values=[pair_root, "early-stop"]), content_type="application/x-parquet"),
        InputData(channel_name="calibration", data_source=Join(on="/", values=[pair_root, "calibration"]), content_type="application/x-parquet"),
        InputData(channel_name="calibration-truth", data_source=Join(on="/", values=[labels_uri, "calibration"]), content_type="application/json"),
    ], wait=False)
    train_step = TrainingStep("TrainCalibratedGBDT", step_args=train_args, cache_config=cache)
    model_uri = train_step.properties.ModelArtifacts.S3ModelArtifacts

    eval_processor = Processor(entrypoint=["python", "/opt/program/cloud/sagemaker/jobs/evaluate.py"],
                               base_job_name="entity-resolution-evaluate", **processing_common)
    eval_args = eval_processor.run(
        inputs=[_s3_input("model", model_uri, "/opt/ml/processing/input/model"),
                _s3_input("pairs", Join(on="/", values=[pair_root, "holdout"]), "/opt/ml/processing/input/pairs"),
                _s3_input("truth", Join(on="/", values=[labels_uri, "holdout", "truth"]), "/opt/ml/processing/input/truth"),
                _s3_input("slices", Join(on="/", values=[labels_uri, "holdout", "slices"]), "/opt/ml/processing/input/slices")],
        outputs=[_s3_output("evaluation", Join(on="/", values=[run_root, "evaluation"]), "/opt/ml/processing/output/evaluation")],
        arguments=["--experiment-id", experiment_id], wait=False,
    )
    evaluation_file = PropertyFile(name="Evaluation", output_name="evaluation", path="evaluation.json")
    eval_step = ProcessingStep("EvaluateLockedHoldout", step_args=eval_args, property_files=[evaluation_file], cache_config=cache)

    export_processor = Processor(entrypoint=["python", "/opt/program/cloud/sagemaker/jobs/export_predictions.py"],
                                 base_job_name="entity-resolution-export", **processing_common)
    export_args = export_processor.run(
        inputs=[_s3_input("model", model_uri, "/opt/ml/processing/input/model"),
                _s3_input("pairs", Join(on="/", values=[pair_root, "test"]), "/opt/ml/processing/input/pairs"),
                _s3_input("required", Join(on="/", values=[labels_uri, "test", "required"]), "/opt/ml/processing/input/required")],
        outputs=[_s3_output("submission", Join(on="/", values=[run_root, "submission"]), "/opt/ml/processing/output/submission")],
        wait=False,
    )
    export_step = ProcessingStep("ExportSubmission", step_args=export_args, cache_config=cache)

    fail_model = FailStep("ModelQualityFailed", error_message="Model macro-F0.5 or singleton false-positive gate failed")
    model_gate = ConditionStep(
        "ModelQualityGate",
        conditions=[
            ConditionGreaterThanOrEqualTo(
                left=JsonGet(step_name=eval_step.name, property_file=evaluation_file, json_path="metrics.model_macro_f05"), right=min_model),
            ConditionLessThanOrEqualTo(
                left=JsonGet(step_name=eval_step.name, property_file=evaluation_file,
                             json_path="metrics.singleton_false_positive_rate"), right=max_singleton_fp),
        ],
        if_steps=[export_step], else_steps=[fail_model],
    )
    fail_candidate = FailStep("CandidateQualityFailed", error_message="Candidate recall or oracle macro-F0.5 gate failed")
    candidate_gate = ConditionStep(
        "CandidateQualityGate",
        conditions=[
            ConditionGreaterThanOrEqualTo(
                left=JsonGet(step_name=quality_step.name, property_file=quality_file, json_path="candidate_recall"), right=min_recall),
            ConditionGreaterThanOrEqualTo(
                left=JsonGet(step_name=quality_step.name, property_file=quality_file, json_path="candidate_oracle_f05"), right=min_oracle),
        ],
        if_steps=[pair_step, train_step, eval_step, model_gate], else_steps=[fail_candidate],
    )
    return SchemaCompatiblePipeline(
        name=pipeline_name, parameters=parameters, steps=[quality_step, candidate_gate], sagemaker_session=session
    )
