"""
Modal Sandbox deployment - A3 full fix with network egress control.

This is the proper fix for A3. Requires moving channel adapters to Sandboxes
with outbound_domain_allowlist. Not yet implemented (Moves 2-4).

Deploy with:   uv run modal deploy modal_app_sandbox.py
"""

from pathlib import Path
import modal

app = modal.App("glc-v1-gateway-sandbox")
LOCAL_GLC = Path(__file__).parent / "glc"

BASE_IMAGE_DIGEST = "debian@sha256:2bc5c236e9b262645cb1fbb8f4b9c991c5f4c7ae6f9e2f8a0c4e8f9f0f8f0f8f"

image = (
    modal.Image.from_registry(BASE_IMAGE_DIGEST, add_python="3.11")
    .run_commands("apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*")
    .pip_install("uv==0.5.18")
    .add_local_file("pyproject.toml", "/root/pyproject.toml")
    .add_local_file("uv.lock", "/root/uv.lock")
    .run_commands("cd /root && uv pip install --system --frozen .")
    .env({"GLC_CONFIG_DIR": "/data/glc", "GLC_DISABLE_DOCS": "1"})
    .add_local_dir(str(LOCAL_GLC), remote_path="/root/glc")
)

data_volume = modal.Volume.from_name("glc-data", create_if_missing=True)
llm_secret = modal.Secret.from_name("glc-llm-keys")

# A3 FIX: Provider domains allowlist
PROVIDER_DOMAINS = [
    "generativelanguage.googleapis.com",
    "integrate.api.nvidia.com",
    "api.groq.com",
    "api.cerebras.ai",
    "openrouter.ai",
    "models.inference.ai.azure.com",
]

sb = modal.Sandbox.create(
    image=image,
    secrets=[llm_secret],
    mounts=[modal.Mount.from_local_dir(str(LOCAL_GLC), remote_path="/root/glc")],
    network_file_systems={"/data": modal.NetworkFileSystem.from_name("glc-data-nfs")},
    # A3 FIX: Egress allowlist
    outbound_domain_allowlist=PROVIDER_DOMAINS,
    timeout=3600,
)


@app.function(image=image)
def deploy_sandbox():
    """Deploy as Sandbox with egress control."""
    import subprocess
    result = subprocess.run(
        ["uvicorn", "glc.main:app", "--host", "0.0.0.0", "--port", "8111"],
        cwd="/root",
        capture_output=True,
        text=True,
    )
    return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
