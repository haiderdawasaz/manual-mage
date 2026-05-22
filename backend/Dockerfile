FROM python:3.11-slim

# 1. Install System Dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmagic1 \
    gcc \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Create a non-root user (Required by HF)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/model_cache

WORKDIR $HOME/app

# 3. Install Python Dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 4. Pre-download AI Models (Baking)
# Ensure the model cache directory exists and is writable
RUN mkdir -p $HF_HOME

# Use snapshot_download to grab files without initializing the model in RAM
RUN python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('openai/clip-vit-base-patch32', local_dir='model_cache/clip'); \
    snapshot_download('Qwen/Qwen3-ASR-0.6B', local_dir='model_cache/qwen')"

# 5. Copy application code
COPY --chown=user . .

# 6. Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]