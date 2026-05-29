# ViralDNA — GitHub Actions Dockerfile
# Runs the pipeline on GitHub Actions ubuntu-latest runner
# NOTE: RVC voice synthesis is skipped here (needs GPU).
#       Voice phases run on local WSL, then files are synced.

FROM python:3.12-slim

# System deps: ffmpeg (video assembly), curl (health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Use UTC container time; pipeline code converts to IST internally
ENV TZ=UTC
ENV PYTHONUNBUFFERED=1

# Create working directory matching local paths
RUN mkdir -p /app/ViralDNA/{cache,audio,videos,thumbnails,credentials,output/runtime}
WORKDIR /app

# Install Python dependencies
COPY modules/requirements.txt /app/modules/requirements.txt
RUN pip install --no-cache-dir -r /app/modules/requirements.txt

# Copy source code
COPY modules/ /app/modules/
COPY run_pipeline_entrypoint.py /app/

# Entrypoint script selects mode via MODE env var
# MODE=spike_check | primetime | normal
ENTRYPOINT ["python3", "/app/run_pipeline_entrypoint.py"]
CMD ["--mode", "normal"]
