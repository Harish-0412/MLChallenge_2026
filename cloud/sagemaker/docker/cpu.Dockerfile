FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/program:/opt/program/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/program
COPY requirements-features.txt requirements-modeling.txt ./
RUN pip install --no-cache-dir -r requirements-modeling.txt
COPY requirements-jobs.txt ./
RUN pip install --no-cache-dir -r requirements-jobs.txt
COPY src ./src
COPY cloud ./cloud

# Training jobs use this default. Processing jobs override the entrypoint.
ENTRYPOINT ["python", "/opt/program/cloud/sagemaker/jobs/train_gbdt.py"]
