import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import schemas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import ToolCall
from services.artifact_service import ArtifactStore

# MCP imports
from mcp import ClientSession

# Artifact threshold: payloads larger than this get stored as artifacts
ARTIFACT_THRESHOLD_BYTES = 4096  # 4 KB

# MCP tool call timeout (seconds)
MCP_TOOL_TIMEOUT = 120  # 2 minutes - generous for fetch_url browser launch


class Action:
    def __init__(self, artifact_store: ArtifactStore = None):
        """
        Initialize the Action service.
        
        Args:
            artifact_store: Optional ArtifactStore instance (defaults to new ArtifactStore())
        """
        self.artifact_store = artifact_store if artifact_store is not None else ArtifactStore()
    
    async def execute(
        self,
        session: ClientSession,
        tool_call: ToolCall,
    ) -> tuple[str, str | None]:
        """
        Execute an MCP tool call with three key behaviors:
        
        1. **Artifact threshold**: Payloads > 4KB are stored as artifacts, returning a descriptor
        2. **art: guard**: Rejects tool calls with "art:..." arguments (artifact handles aren't paths)
        3. **MCP dispatch**: Calls the actual MCP tool and collapses result to text
        
        Args:
            session: Active MCP ClientSession
            tool_call: ToolCall object with name and arguments
        
        Returns:
            tuple[str, str | None]:
                - result_text: The tool result or error message
                - artifact_id: Artifact ID if created (format "art:<int>"), or None
        """
        # Behavior 2: Guard against art: prefix in arguments
        for key, value in tool_call.arguments.items():
            if isinstance(value, str) and value.startswith("art:"):
                error_msg = (
                    f"Error: Artifact handle '{value}' detected in argument '{key}'. "
                    f"Artifact handles (art:...) are NOT file paths or URLs. "
                    f"They reference the internal artifact store. "
                    f"MCP tools require REAL file paths or URLs. "
                    f"If you need the content of {value}, it should be in ATTACHED ARTIFACTS."
                )
                return error_msg, None
        
        # Behavior 3: Real MCP dispatch with timeout
        try:
            # Wrap call_tool in timeout to prevent indefinite hangs
            result = await asyncio.wait_for(
                session.call_tool(tool_call.name, arguments=tool_call.arguments or {}),
                timeout=MCP_TOOL_TIMEOUT
            )

            # Extract text from first content block (standard MCP pattern from agent5.py)
            # MCP returns content blocks as objects with .text attribute
            if result.content:
                result_text = result.content[0].text
            else:
                result_text = ""

        except asyncio.TimeoutError:
            # Tool call timed out
            error_msg = (
                f"Tool execution timed out after {MCP_TOOL_TIMEOUT}s: "
                f"{tool_call.name}({tool_call.arguments})\n"
                f"The MCP tool did not respond within the timeout period."
            )
            return error_msg, None

        except Exception as e:
            # Tool execution failed
            error_msg = f"Tool execution failed: {tool_call.name}({tool_call.arguments})\nError: {str(e)}"
            return error_msg, None
        
        # Behavior 1: Artifact threshold check
        result_bytes = result_text.encode('utf-8')
        
        if len(result_bytes) > ARTIFACT_THRESHOLD_BYTES:
            # Store as artifact
            artifact_id = self.artifact_store.put(
                result_bytes,
                content_type="text/plain",
                source=f"Tool Result:{tool_call.name}",
                descriptor=f"Result from {tool_call.name}({_format_args(tool_call.arguments)})"
            )
            
            # Create preview (first 200 chars)
            preview = result_text[:200]
            if len(result_text) > 200:
                preview += "..."
            
            # Return descriptor
            descriptor = f"[artifact {artifact_id}, {len(result_bytes)} bytes] preview: {preview}"
            return descriptor, artifact_id
        else:
            # Return text directly (no artifact)
            return result_text, None


def _format_args(arguments: dict, max_len: int = 50) -> str:
    """
    Format tool arguments for display, truncating if too long.
    
    Args:
        arguments: Tool arguments dictionary
        max_len: Maximum length before truncation
    
    Returns:
        Formatted argument string
    """
    import json
    
    args_str = json.dumps(arguments)
    if len(args_str) > max_len:
        return args_str[:max_len] + "..."
    return args_str
