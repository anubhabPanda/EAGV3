"""Gemini Agent with FastMCP integration."""
import os
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
import asyncio
import json


class GeminiAgent:
    """Gemini-powered LLM agent with MCP tool access."""
    
    def __init__(self, mcp_client=None):
        """
        Initialize Gemini agent.

        Args:
            mcp_client: FastMCP client for tool access
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=api_key)
        # Use a stable model - check available models at https://ai.google.dev/gemini-api/docs/models
        self.model_name = "gemini-3.1-flash-lite-preview"  # Stable and reliable
        self.mcp_client = mcp_client
        self.conversation_history = []
        self.system_instruction = None  # Will be set when tools are loaded

        print(f"[AGENT] Initialized with model: {self.model_name}")
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools from MCP server."""
        if not self.mcp_client:
            return []

        try:
            # MCP list_tools returns a ListToolsResult object
            result = await self.mcp_client.list_tools()

            # Convert to list of dicts
            tools_list = []
            if hasattr(result, 'tools'):
                for tool in result.tools:
                    tool_dict = {
                        "name": tool.name,
                        "description": tool.description if hasattr(tool, 'description') else "",
                    }
                    if hasattr(tool, 'inputSchema'):
                        tool_dict["inputSchema"] = tool.inputSchema
                    tools_list.append(tool_dict)

            return tools_list
        except Exception as e:
            print(f"Error getting tools: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _convert_mcp_result_to_dict(self, result: Any) -> Dict[str, Any]:
        """
        Convert MCP CallToolResult to a plain dictionary that Gemini can process.

        Args:
            result: MCP result (could be CallToolResult or other types)

        Returns:
            Plain dictionary
        """
        # If it's already a dict, return it
        if isinstance(result, dict):
            return result

        # If it's a string, number, bool, return as-is wrapped in dict
        if isinstance(result, (str, int, float, bool, type(None))):
            return {"result": result}

        # If it's a list, convert items
        if isinstance(result, list):
            return {"result": [self._convert_mcp_result_to_dict(item) if not isinstance(item, (str, int, float, bool, type(None))) else item for item in result]}

        # If it's an MCP CallToolResult object
        if hasattr(result, 'content'):
            # Extract content from MCP result
            content = result.content
            if isinstance(content, list):
                # Join text content if it's a list of text items
                text_parts = []
                for item in content:
                    if hasattr(item, 'text'):
                        text_parts.append(item.text)
                    elif isinstance(item, dict) and 'text' in item:
                        text_parts.append(item['text'])
                    elif isinstance(item, str):
                        text_parts.append(item)
                return {"result": "\n".join(text_parts) if text_parts else str(content)}
            else:
                return {"result": str(content)}

        # Fallback: convert to string
        return {"result": str(result)}

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool via MCP client.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if not self.mcp_client:
            return {"error": "MCP client not configured"}

        try:
            result = await self.mcp_client.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            return {"error": f"Tool call failed: {str(e)}"}
    
    def _build_system_instruction(self, tools: List[Dict[str, Any]]) -> str:
        """
        Build system instruction with available tools.

        Args:
            tools: List of available MCP tools

        Returns:
            System instruction string
        """
        if not tools:
            return "You are a helpful AI assistant."

        # Format tool names and descriptions
        tool_list = []
        for tool in tools:
            name = tool.get("name", "unknown")
            description = tool.get("description", "")
            tool_list.append(f"  - {name}: {description}")

        tools_text = "\n".join(tool_list)

        system_prompt = f"""You are provided with the following tools:

{tools_text}

Always use the provided tools to answer the user's request. Never assume anything.

When a user asks a question that requires information you don't have, always use the appropriate tool to get that information. Be thorough and accurate in your responses.

IMPORTANT NOTES ABOUT THE DASHBOARD TOOL:
- The 'dashboard' tool opens an interactive UI where the USER can input data and visualize it
- The dashboard is NOT for displaying data you've collected - it's for the user to interact with
- When you call 'dashboard', tell the user: "I've opened the interactive dashboard in the right panel. You can use it to visualize data by filling in the forms."
- DO NOT expect the dashboard to automatically show data you've searched or created
- The dashboard has these sections:
  * Weather Information: User can enter a location to see weather
  * Search Results: User can enter a search query
  * Satellite Images: User can enter coordinates to see satellite imagery

If the user wants to see visualized data you've collected:
- Present the data in your text response with clear formatting
- Tell them they can use the dashboard tool separately if they want to visualize other data"""

        return system_prompt

    def convert_tools_to_gemini_format(self, tools: List[Dict[str, Any]]) -> List[types.Tool]:
        """
        Convert MCP tools to Gemini function calling format.

        Args:
            tools: List of MCP tool definitions

        Returns:
            List of Gemini Tool objects
        """
        if not tools:
            return []

        function_declarations = []

        for tool in tools:
            # Get input schema
            input_schema = tool.get("inputSchema", {})

            # Build parameters for Gemini
            parameters = {
                "type": "object",
                "properties": input_schema.get("properties", {}),
            }

            # Add required fields if present
            if "required" in input_schema and input_schema["required"]:
                parameters["required"] = input_schema["required"]

            function_declaration = types.FunctionDeclaration(
                name=tool.get("name", ""),
                description=tool.get("description", ""),
                parameters=parameters
            )
            function_declarations.append(function_declaration)

        # Return single Tool with all function declarations
        if function_declarations:
            return [types.Tool(function_declarations=function_declarations)]

        return []
    
    async def chat(self, message: str, max_iterations: int = 15) -> Dict[str, Any]:
        """
        Send a message to the agent and handle tool calls.

        Args:
            message: User message
            max_iterations: Maximum number of tool calling iterations

        Returns:
            Response dictionary with text and metadata
        """
        print(f"\n[AGENT] Received message: {message[:100]}...")

        # Add user message to history using types.Content
        self.conversation_history.append(
            types.Content(
                role="user",
                parts=[types.Part(text=message)]
            )
        )
        print(f"[AGENT] Conversation history length: {len(self.conversation_history)}")

        # Get available tools
        print("[AGENT] Getting available tools...")
        mcp_tools = await self.get_available_tools()
        print(f"[AGENT] Found {len(mcp_tools)} MCP tools")

        gemini_tools = self.convert_tools_to_gemini_format(mcp_tools) if mcp_tools else None
        print(f"[AGENT] Converted to Gemini format: {len(gemini_tools) if gemini_tools else 0} tool objects")

        # Build system instruction with available tools
        if self.system_instruction is None:
            self.system_instruction = self._build_system_instruction(mcp_tools)
            print(f"[AGENT] System instruction set ({len(self.system_instruction)} chars)")

        iteration = 0
        tool_calls_made = []

        while iteration < max_iterations:
            iteration += 1
            print(f"\n[AGENT] === Iteration {iteration}/{max_iterations} ===")

            try:
                # Create config
                config = {
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }

                # Add system instruction if available
                if self.system_instruction:
                    config["system_instruction"] = self.system_instruction

                if gemini_tools:
                    config["tools"] = gemini_tools
                    print(f"[AGENT] Using {len(gemini_tools)} tool(s)")

                print(f"[AGENT] Calling Gemini model: {self.model_name}")
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=self.conversation_history,
                    config=types.GenerateContentConfig(**config)
                )
                print(f"[AGENT] Received response from Gemini")

            except Exception as e:
                print(f"[AGENT] ERROR generating content: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "text": f"Error generating response: {str(e)}",
                    "tool_calls": tool_calls_made,
                    "iterations": iteration,
                    "error": str(e)
                }
            
            # Check for function calls
            function_calls = []
            if response.candidates and len(response.candidates) > 0:
                print(f"[AGENT] Checking response parts...")
                for part in response.candidates[0].content.parts:
                    print(f"[AGENT] Part type: {type(part)}, has function_call: {hasattr(part, 'function_call')}")
                    if hasattr(part, 'function_call') and part.function_call:
                        function_calls.append(part.function_call)
                        print(f"[AGENT] Found function call: {part.function_call.name}")

            if not function_calls:
                # No more tool calls, return final response
                print(f"[AGENT] No function calls, generating final response")

                # Add the full model response to preserve thought_signature
                self.conversation_history.append(response.candidates[0].content)

                response_text = ""
                try:
                    if hasattr(response, 'text'):
                        response_text = response.text
                    elif response.candidates and len(response.candidates) > 0:
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, 'text'):
                                response_text += part.text

                    print(f"[AGENT] Response text length: {len(response_text)}")

                except Exception as e:
                    print(f"[AGENT] Error extracting text: {e}")
                    response_text = "Sorry, I encountered an error processing the response."

                print(f"[AGENT] Returning response with {len(tool_calls_made)} tool calls")
                return {
                    "text": response_text,
                    "tool_calls": tool_calls_made,
                    "iterations": iteration
                }
            
            # CRITICAL: Add the full model Content object to preserve thought_signature
            # This is the key fix from Session 3!
            print(f"[AGENT] Adding full candidate.content to preserve thought_signature")
            self.conversation_history.append(response.candidates[0].content)

            # Execute tool calls
            print(f"[AGENT] Executing {len(function_calls)} tool call(s)")
            function_responses = []

            for func_call in function_calls:
                tool_name = func_call.name
                tool_args = dict(func_call.args) if func_call.args else {}
                func_id = func_call.id if hasattr(func_call, 'id') else None

                print(f"[AGENT] Calling tool: {tool_name} with args: {tool_args}")
                if func_id:
                    print(f"[AGENT] Function Call ID: {func_id}")

                # Call the tool
                result = await self.call_tool(tool_name, tool_args)
                print(f"[AGENT] Tool result type: {type(result)}")

                # Convert MCP result to plain dict for Gemini
                result_dict = self._convert_mcp_result_to_dict(result)
                print(f"[AGENT] Converted result type: {type(result_dict)}")

                tool_calls_made.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "result": result_dict
                })

                # Create FunctionResponse with matching ID (required for Gemini 3.x)
                func_response = types.FunctionResponse(
                    name=tool_name,
                    response=result_dict
                )
                # Set ID if available (Gemini 3 requires this to match with the call)
                if func_id:
                    func_response.id = func_id

                function_responses.append(
                    types.Part(function_response=func_response)
                )

            # Add function responses as user content (Gemini expects this format)
            self.conversation_history.append(
                types.Content(
                    role="user",
                    parts=function_responses
                )
            )

            print(f"[AGENT] Tool execution complete, continuing loop...")

        # Max iterations reached
        print(f"[AGENT] Max iterations ({max_iterations}) reached")
        return {
            "text": "Maximum tool calling iterations reached. Please try rephrasing your question.",
            "tool_calls": tool_calls_made,
            "iterations": iteration,
            "error": "max_iterations_exceeded"
        }

    def reset_conversation(self):
        """Reset conversation history."""
        self.conversation_history = []

    def set_system_instruction(self, instruction: str):
        """
        Set a custom system instruction.

        Args:
            instruction: Custom system instruction text
        """
        self.system_instruction = instruction
        print(f"[AGENT] Custom system instruction set ({len(instruction)} chars)")

    def get_system_instruction(self) -> Optional[str]:
        """
        Get the current system instruction.

        Returns:
            Current system instruction or None
        """
        return self.system_instruction
