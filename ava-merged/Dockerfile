# AVA NextGen — CORRECTED Dockerfile
# SECURITY: no PIN hash, no secret, and no default secret is set here.
# The vault PIN hash must arrive via the environment at run time
# (compose passes ${AVA_VAULT_PIN_HASH} through; it is never baked
# into the image). If it is absent, the vault stays locked.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ ./services/
COPY services_stdlib/ ./services_stdlib/
COPY jga_auto/ ./jga_auto/
COPY tests/ ./tests/
COPY ava_merged.py gateway.py healthcheck.py dashboard.py ./

ENV PYTHONUNBUFFERED=1
# VAULT_DATA_DIR is set by compose to /app/vault_data (the volume).
# It is intentionally NOT set here, so a plain `docker run` without
# the volume still uses a local ./vault_data directory.

CMD ["python", "ava_merged.py"]
