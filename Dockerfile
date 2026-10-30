# ==============================================================================
# Stage 1: Builder - Build dependencies & bake ONNX models
# ==============================================================================
FROM python:3.14.7-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Build wheels for production dependencies
COPY requirements/ requirements/
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements/01-base.txt

# Download offline ONNX OCR models and verify checksums
RUN mkdir -p /models/ocr && \
    curl -fsSL -o /models/ocr/yolo-v9-t-384-license-plates-end2end.onnx \
        https://github.com/ankandrew/open-image-models/releases/download/assets/yolo-v9-t-384-license-plates-end2end.onnx && \
    curl -fsSL -o /models/ocr/yolo-v9-t-640-license-plates-end2end.onnx \
        https://github.com/ankandrew/open-image-models/releases/download/assets/yolo-v9-t-640-license-plates-end2end.onnx && \
    curl -fsSL -o /models/ocr/cct_xs_v2_global.onnx \
        https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates/cct_xs_v2_global.onnx && \
    curl -fsSL -o /models/ocr/cct_xs_v2_global_plate_config.yaml \
        https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates/cct_xs_v2_global_plate_config.yaml && \
    curl -fsSL -o /models/ocr/global_mobile_vit_v2_ocr.onnx \
        https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates/global_mobile_vit_v2_ocr.onnx && \
    curl -fsSL -o /models/ocr/global_mobile_vit_v2_ocr_config.yaml \
        https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates/global_mobile_vit_v2_ocr_config.yaml && \
    echo "888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8  /models/ocr/yolo-v9-t-384-license-plates-end2end.onnx" > /tmp/ocr_models.sha256 && \
    echo "c3c1026ca7d0585dd88084d68182dd897113712fa734ae1557ca70174440c076  /models/ocr/yolo-v9-t-640-license-plates-end2end.onnx" >> /tmp/ocr_models.sha256 && \
    echo "8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44  /models/ocr/cct_xs_v2_global.onnx" >> /tmp/ocr_models.sha256 && \
    echo "0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6  /models/ocr/cct_xs_v2_global_plate_config.yaml" >> /tmp/ocr_models.sha256 && \
    echo "e2fe5946c02e73901f73d21b3b7223a0c3e3b02059d4964fbf279b01af38d63c  /models/ocr/global_mobile_vit_v2_ocr.onnx" >> /tmp/ocr_models.sha256 && \
    echo "202b90f2a1f3a0d486b8f1fbd5cdc2f19f4f4881a094f086b983976ed3108aaf  /models/ocr/global_mobile_vit_v2_ocr_config.yaml" >> /tmp/ocr_models.sha256 && \
    sha256sum -c /tmp/ocr_models.sha256 && rm /tmp/ocr_models.sha256

# ==============================================================================
# Stage 2: Runtime - Minimal unprivileged production image
# ==============================================================================
FROM python:3.14.7-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime system dependencies:
# - libgl1 removed: fast-alpr and open-image-models use opencv-python-headless
# - curl: for healthcheck probe
# - gosu: for graceful root-to-non-root privilege drop when requested
# - libglib2.0-0, libgomp1: for ONNX Runtime CPU multi-threading
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and group (UID 10001, GID 10001)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

WORKDIR /app

# Install pre-built production wheels via BuildKit bind-mount (zero persistent /wheels layer)
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*

# Populate models and create cache symlinks and directories in a single consolidated RUN layer
COPY --from=builder --chown=appuser:appgroup /models/ocr /app/models/ocr
RUN mkdir -p \
        /home/appuser/.cache/open-image-models/yolo-v9-t-384-license-plate-end2end \
        /home/appuser/.cache/open-image-models/yolo-v9-t-640-license-plate-end2end \
        /home/appuser/.cache/fast-plate-ocr/cct-xs-v2-global-model \
        /home/appuser/.cache/fast-plate-ocr/global-plates-mobile-vit-v2-model \
        /app/staticfiles && \
    ln -s /app/models/ocr/yolo-v9-t-384-license-plates-end2end.onnx \
        /home/appuser/.cache/open-image-models/yolo-v9-t-384-license-plate-end2end/yolo-v9-t-384-license-plates-end2end.onnx && \
    ln -s /app/models/ocr/yolo-v9-t-640-license-plates-end2end.onnx \
        /home/appuser/.cache/open-image-models/yolo-v9-t-640-license-plate-end2end/yolo-v9-t-640-license-plates-end2end.onnx && \
    ln -s /app/models/ocr/cct_xs_v2_global.onnx \
        /home/appuser/.cache/fast-plate-ocr/cct-xs-v2-global-model/cct_xs_v2_global.onnx && \
    ln -s /app/models/ocr/cct_xs_v2_global_plate_config.yaml \
        /home/appuser/.cache/fast-plate-ocr/cct-xs-v2-global-model/cct_xs_v2_global_plate_config.yaml && \
    ln -s /app/models/ocr/global_mobile_vit_v2_ocr.onnx \
        /home/appuser/.cache/fast-plate-ocr/global-plates-mobile-vit-v2-model/global_mobile_vit_v2_ocr.onnx && \
    ln -s /app/models/ocr/global_mobile_vit_v2_ocr_config.yaml \
        /home/appuser/.cache/fast-plate-ocr/global-plates-mobile-vit-v2-model/global_mobile_vit_v2_ocr_config.yaml && \
    chown -R appuser:appgroup /home/appuser /app/staticfiles

# Copy entrypoint script
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Copy runtime application code only (no tests/, docs/, .github/, .agents/)
COPY --chown=appuser:appgroup apps/ /app/apps/
COPY --chown=appuser:appgroup config/ /app/config/
COPY --chown=appuser:appgroup docker/ /app/docker/
COPY --chown=appuser:appgroup db/01-schema.sql db/02-seed.sql /app/db/
COPY --chown=appuser:appgroup manage.py /app/manage.py

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
  CMD curl -f http://127.0.0.1:8000/api/health/ || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["gunicorn", "-c", "docker/gunicorn.conf.py", "config.wsgi:application"]

# ==============================================================================
# Stage 3: Dev / Test - Target for testing, linting and type checking in container
# ==============================================================================
FROM runtime AS dev

USER root

# Install development & test dependencies
COPY requirements/02-dev.txt /tmp/requirements/02-dev.txt
COPY requirements/01-base.txt /tmp/requirements/01-base.txt
RUN pip install --no-cache-dir -r /tmp/requirements/02-dev.txt && \
    rm -rf /tmp/requirements

# Copy test suites, documentation, and database artifacts
COPY --chown=appuser:appgroup tests/ /app/tests/
COPY --chown=appuser:appgroup docs/ /app/docs/
COPY --chown=appuser:appgroup db/ /app/db/

# Defense-in-depth environment variables for non-root testing
ENV COVERAGE_FILE=/tmp/.coverage \
    PYTEST_ADDOPTS="-o cache_dir=/tmp/.pytest_cache"

USER appuser

# Alias stage 'test' to point to 'dev' for compatibility with all build targets
FROM dev AS test
