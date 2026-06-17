FROM python:3.11-slim-bookworm

WORKDIR /app

# TensorFlow runtime dependency on Debian slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CUDA_VISIBLE_DEVICES=-1

# Install Python deps first (better layer cache)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

# App code (build context must be repo root: docker build -f backend/Dockerfile .)
COPY backend/ /app/backend/

# PINN runtime artifacts (sibling ../model path expected by scheduler + main.py)
COPY model/forecaster.py model/utils.py /app/model/
COPY model/scalers.pkl model/sensor_info.pkl model/pinn_model_best.h5 /app/model/
COPY model/sliot_dataset /app/model/sliot_dataset
COPY model/prediction_results.csv model/training_history.csv /app/model/

WORKDIR /app/backend

EXPOSE 8000

COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
