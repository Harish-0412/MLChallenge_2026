ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/program:/opt/program/src \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /opt/program
COPY requirements-neural.txt ./
RUN pip install --no-cache-dir -r requirements-neural.txt
COPY src ./src
COPY cloud ./cloud

ENTRYPOINT ["python", "/opt/program/cloud/sagemaker/jobs/train_biencoder.py"]

