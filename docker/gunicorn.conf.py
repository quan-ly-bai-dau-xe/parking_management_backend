"""
Gunicorn configuration for Parking Management Backend (Milestone 1 - P1 & P3).
Worker class: gthread with optimized worker/thread sizing, memory hygiene,
and post_fork ONNX runtime warm-up.
"""

import os

# Server Socket
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
backlog = int(os.getenv("GUNICORN_BACKLOG", 2048))

# Worker Processes & Threads
# Worker class gthread optimizes CPU usage during native C++ OCR execution (GIL released)
worker_class = "gthread"
workers = int(os.getenv("GUNICORN_WORKERS", 4))
threads = int(os.getenv("GUNICORN_THREADS", 6))

# Worker Lifecycle & Memory Hygiene (H3)
# Default max_requests=0 to eliminate restart storms and preserve HTTP keep-alive.
# Memory-watch mechanism in post_request replaces arbitrary request-count restarts.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 0))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 100))
timeout = int(os.getenv("GUNICORN_TIMEOUT", 30))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 15))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))
memory_limit_mb = int(os.getenv("GUNICORN_MEMORY_LIMIT_MB", 1536))

# Logging Configuration
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" rt=%(L)ss'
)

# Process Naming
proc_name = "parking_web_gunicorn"


def post_fork(server, worker):
    """Hook executed immediately after a worker process is forked."""
    server.log.info(f"Gunicorn worker spawned (pid: {worker.pid})")
    try:
        import django
        from django.conf import settings

        if not settings.configured:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
            django.setup()

        from apps.parking.services.ocr import warmup_ocr

        warmup_ocr()
        server.log.info(
            f"Worker {worker.pid} ONNX model warm-up completed successfully."
        )

        # Pre-warm 12MP image decoding pipeline & memory arena (touch physical pages)
        try:
            import io

            from django.core.files.uploadedfile import SimpleUploadedFile
            from PIL import Image

            from apps.parking.services.upload import process_uploaded_image

            raw_img_12mp = Image.new("RGB", (4000, 3000), color=(100, 150, 200))
            buf = io.BytesIO()
            raw_img_12mp.save(buf, format="JPEG", quality=85)
            dummy_file = SimpleUploadedFile(
                "warmup_12mp.jpg", buf.getvalue(), content_type="image/jpeg"
            )
            _ = process_uploaded_image(dummy_file)
            server.log.info(
                f"Worker {worker.pid} 12MP image decode memory arena pre-warmed successfully."
            )
        except Exception as exc:
            server.log.warning(
                f"Worker {worker.pid} 12MP decode warmup encountered exception: {exc}"
            )
    except Exception as exc:
        server.log.warning(
            f"Worker {worker.pid} ONNX warm-up encountered exception: {exc}"
        )


def post_request(worker, req, environ, resp):
    """
    H3 Memory-Watch: Periodically samples worker RSS resident memory.
    If RSS exceeds memory_limit_mb, triggers a graceful worker exit
    so Gunicorn master can replace it cleanly without connection drops.
    """
    if getattr(worker, "_req_count", None) is None:
        worker._req_count = 0
    worker._req_count += 1

    # Check RSS every 100 requests to avoid getrusage syscall overhead
    if worker._req_count % 100 == 0:
        try:
            import resource

            # ru_maxrss is in KiB on Linux
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_mb = rss_kb / 1024.0
            if rss_mb > memory_limit_mb:
                worker.log.warning(
                    f"Worker {worker.pid} RSS ({rss_mb:.1f} MB) exceeded limit ({memory_limit_mb} MB). "
                    "Triggering staggered graceful restart."
                )
                worker.alive = False
        except Exception:
            pass
