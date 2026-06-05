import sys
import httpx
from pathlib import Path


def ensure_llm_gateway(base_url: str = "http://localhost:8107", timeout: float = 5.0) -> None:
    """
    Ensure the LLM gateway V7 is available.

    This function checks if the LLM gateway is running and accessible by calling
    the /v1/routers endpoint. If not running, it raises an error with instructions
    on how to start it.

    Args:
        base_url: The base URL of the gateway (default: http://localhost:8107)
        timeout: Timeout in seconds for the health check (default: 5.0)

    Raises:
        RuntimeError: If the gateway is not running or not accessible
    """
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/v1/routers", timeout=timeout)
        response.raise_for_status()
        data = response.json()

        # Verify response structure - should have router pool info
        if not isinstance(data, dict):
            raise RuntimeError(
                f"LLM Gateway V7 at {base_url} returned invalid response format"
            )

        print(f"✓ LLM Gateway V7 is running at {base_url}")
        return

    except httpx.ConnectError:
        # Gateway is not running
        gateway_path = Path(__file__).resolve().parent.parent / "resources" / "llm_gatewayV7"
        error_msg = (
            f"LLM Gateway V7 is not running at {base_url}.\n\n"
            f"To start the gateway:\n"
            f"  cd {gateway_path}\n"
            f"  ./run.sh\n"
            f"  # or: ./.venv/bin/python main.py\n\n"
            f"The gateway should start on port 8107 (default for V7).\n"
            f"V1 uses port 8099, V2 uses 8100, V3 uses 8101 - all can coexist."
        )
        raise RuntimeError(error_msg) from None

    except httpx.TimeoutException:
        raise RuntimeError(
            f"LLM Gateway V7 at {base_url} timed out after {timeout}s. "
            f"The gateway may be overloaded or stuck."
        ) from None

    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"LLM Gateway V7 at {base_url} returned error status {e.response.status_code}: "
            f"{e.response.text}"
        ) from None

    except Exception as e:
        raise RuntimeError(
            f"Failed to connect to LLM Gateway V7 at {base_url}: {e}"
        ) from None
