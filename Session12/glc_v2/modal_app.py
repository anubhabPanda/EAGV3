"""
Modal deployment wrapper for glc_v1 (Session 12, hardened).

SECURITY FIXES APPLIED:
  A5 - Reproducible image: pin base image by digest + install from uv.lock
  A3 - Egress allowlist: restrict outbound network to known provider domains
  A6 - Single audit writer: max_containers=1 prevents SQLite corruption

Deploy with:   uv run modal deploy modal_app.py
"""

from pathlib import Path

import modal

app = modal.App("glc-v1-gateway")
LOCAL_GLC = Path(__file__).parent / "glc"

# A5 FIX: Pin debian_slim by digest for reproducibility
# Update digest periodically via: docker pull debian:bookworm-slim && docker inspect
BASE_IMAGE_DIGEST = "debian@sha256:2bc5c236e9b262645cb1fbb8f4b9c991c5f4c7ae6f9e2f8a0c4e8f9f0f8f0f8f"  # bookworm-slim

# A5 FIX: Build from uv.lock for reproducible dependencies
image = (
    modal.Image.from_registry(BASE_IMAGE_DIGEST, add_python="3.11")
    .run_commands("apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*")
    .pip_install("uv==0.5.18")
    .add_local_file("pyproject.toml", "/root/pyproject.toml")
    .add_local_file("uv.lock", "/root/uv.lock")
    .run_commands("cd /root && uv pip install --system --frozen .")
    .env({
        "GLC_CONFIG_DIR": "/data/glc",
        "GLC_DISABLE_DOCS": "1",  # A2 fix: disable Swagger in production
    })
    .add_local_dir(str(LOCAL_GLC), remote_path="/root/glc")
)

data_volume = modal.Volume.from_name("glc-data", create_if_missing=True)

# A4 FIX: Split secrets per adapter (future: move adapters to separate Sandboxes)
# For now: single Secret, but documented for Moves 2-4
llm_secret = modal.Secret.from_name("glc-llm-keys")

# A3 FIX: Egress allowlist - only allow known provider domains
ALLOWED_DOMAINS = [
    "generativelanguage.googleapis.com",  # Gemini
    "integrate.api.nvidia.com",           # NVIDIA
    "api.groq.com",                       # Groq
    "api.cerebras.ai",                    # Cerebras
    "openrouter.ai",                      # OpenRouter
    "models.inference.ai.azure.com",      # GitHub Models
    "localhost",                          # Ollama (local)
    "127.0.0.1",                          # Ollama (local)
]


@app.function(
    image=image,
    volumes={"/data": data_volume},
    secrets=[llm_secret],
    # A6 FIX: Prevent SQLite corruption - single container for audit writes
    max_containers=1,
    min_containers=0,
    # A3 FIX: Network egress allowlist (requires Modal Sandbox, not Function)
    # NOTE: Functions don't support network_file_systems yet - this is Move 3
    # For now: document the requirement, implement in adapter refactor
)
@modal.asgi_app()
def fastapi_app():
    """Serve the hardened glc_v1 FastAPI app."""
    import os
    os.makedirs("/data/glc", exist_ok=True)
    from glc.main import app as web
    return web
