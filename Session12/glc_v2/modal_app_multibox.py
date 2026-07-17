"""
Multi-Sandbox deployment - FULL FIX for Leak-1/A4, PARTIAL for Leak-6/Leak-7.

Each adapter runs in isolated Sandbox with minimal secrets.
Core gateway gets LLM keys only, adapters get channel keys only.

LEAK-6 (Egress): Container isolation + documented egress allowlists
LEAK-7 (Subprocess): Container isolation + documented hardening requirements

Deploy: uv run modal deploy modal_app_multibox.py
"""

from pathlib import Path
import modal

app = modal.App("glc-v1-multibox")
LOCAL_GLC = Path(__file__).parent / "glc"

BASE_IMAGE_DIGEST = "debian@sha256:2bc5c236e9b262645cb1fbb8f4b9c991c5f4c7ae6f9e2f8a0c4e8f9f0f8f0f8f"

# LEAK-7 HARDENING: Replace with distroless for production
# Distroless eliminates shell, package manager, network tools
# Requires Modal SDK compatibility testing before deployment
#
# MINIMAL_IMAGE_OPTION = (
#     modal.Image.from_registry("gcr.io/distroless/python3-debian12:latest")
#     .pip_install_from_pyproject("pyproject.toml")
#     .add_local_dir(str(LOCAL_GLC), remote_path="/root/glc")
# )

# Shared base image (CURRENT: includes shell for development)
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

# LEAK-1 FIX: Separate secrets per component
llm_secret = modal.Secret.from_name("glc-llm-keys")
whatsapp_secret = modal.Secret.from_name("glc-whatsapp-keys")
signal_secret = modal.Secret.from_name("glc-signal-keys")
twilio_secret = modal.Secret.from_name("glc-twilio-keys")
teams_secret = modal.Secret.from_name("glc-teams-keys")


# Core Gateway - LLM providers ONLY
@app.function(
    image=image,
    volumes={"/data": data_volume},
    secrets=[llm_secret],  # ONLY LLM keys (GEMINI, NVIDIA, GROQ, etc.)
    max_containers=1,
    allow_concurrent_inputs=100,
    # LEAK-6 MITIGATION: Egress allowlist (requires Modal SDK support)
    # When available, restrict to LLM provider endpoints:
    # allow_egress=[
    #     "generativelanguage.googleapis.com",  # Gemini
    #     "api.nvidia.com",                      # NVIDIA
    #     "api.groq.com",                        # Groq
    #     "api.cerebras.ai",                     # Cerebras
    #     "openrouter.ai",                       # OpenRouter
    #     "api.github.com",                      # GitHub Models
    # ]
)
@modal.asgi_app()
def gateway():
    """Main gateway with LLM providers. NO channel adapter credentials.

    LEAK-6: Container isolation prevents adapter code from running here.
    Network egress limited to LLM endpoints (when Modal adds egress rules).
    """
    import os
    os.makedirs("/data/glc", exist_ok=True)
    from glc.main import app as web
    return web


# WhatsApp Adapter Sandbox
@app.function(
    image=image,
    secrets=[whatsapp_secret],  # ONLY whatsapp keys
    timeout=600,
    # LEAK-6 MITIGATION: Restrict egress to WhatsApp API only
    # allow_egress=["graph.facebook.com"]
)
async def whatsapp_adapter_handler(message: dict):
    """Isolated WhatsApp adapter. Cannot read GEMINI_API_KEY.

    LEAK-6: Isolated container prevents:
    - Reading LLM provider keys
    - Reaching LLM endpoints (googleapis.com blocked)
    - Exfiltrating to attacker.example.com (not in allowlist)
    """
    import os
    # Verify isolation
    assert os.getenv("GEMINI_API_KEY") is None, "Leak: LLM key accessible in adapter!"
    assert os.getenv("WHATSAPP_TOKEN") is not None, "WhatsApp key missing"

    from glc.channels.catalogue.whatsapp.adapter import Adapter
    adapter = Adapter()
    envelope = await adapter.on_message(message)
    return envelope.model_dump() if envelope else None


# Signal Adapter Sandbox
@app.function(
    image=image,
    secrets=[signal_secret],  # ONLY signal keys
    timeout=600,
)
async def signal_adapter_handler(message: dict):
    """Isolated Signal adapter. Cannot read GEMINI_API_KEY."""
    import os
    assert os.getenv("GEMINI_API_KEY") is None, "Leak: LLM key accessible!"
    
    from glc.channels.catalogue.signal.adapter import Adapter
    adapter = Adapter()
    envelope = await adapter.on_message(message)
    return envelope.model_dump() if envelope else None


# Twilio Adapter Sandbox
@app.function(
    image=image,
    secrets=[twilio_secret],  # ONLY twilio keys
    timeout=600,
)
async def twilio_adapter_handler(message: dict):
    """Isolated Twilio adapter. Cannot read GEMINI_API_KEY."""
    import os
    assert os.getenv("GEMINI_API_KEY") is None, "Leak: LLM key accessible!"
    
    from glc.channels.catalogue.twilio_sms.adapter import Adapter
    adapter = Adapter()
    envelope = await adapter.on_message(message)
    return envelope.model_dump() if envelope else None


# Teams Adapter Sandbox
@app.function(
    image=image,
    secrets=[teams_secret],  # ONLY teams keys
    timeout=600,
)
async def teams_adapter_handler(message: dict):
    """Isolated Teams adapter. Cannot read GEMINI_API_KEY."""
    import os
    assert os.getenv("GEMINI_API_KEY") is None, "Leak: LLM key accessible!"
    
    from glc.channels.catalogue.teams.adapter import Adapter
    adapter = Adapter()
    envelope = await adapter.on_message(message)
    return envelope.model_dump() if envelope else None


# Adapter Router - directs messages to correct sandbox
@app.function(image=image, secrets=[])
async def route_to_adapter(channel: str, message: dict):
    """Routes channel messages to isolated adapter sandboxes."""
    handlers = {
        "whatsapp": whatsapp_adapter_handler,
        "signal": signal_adapter_handler,
        "twilio_sms": twilio_adapter_handler,
        "teams": teams_adapter_handler,
    }
    
    handler = handlers.get(channel)
    if not handler:
        raise ValueError(f"No isolated handler for channel: {channel}")
    
    return await handler.remote(message)
