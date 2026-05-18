# Session 4: Multi-Service AI Agent System (MCP via SSE)

## Overview

This session contains a complete multi-service AI agent system with three integrated services:

1. **Gemini LLM Agent** - AI agent powered by Gemini 2.0 Flash Exp
2. **FastMCP Server** - Remote tool provider via SSE transport
3. **FastAPI Backend** - REST API wrapper for the agent

## Architecture

The system uses **SSE (Server-Sent Events)** transport for MCP communication:

```
Client → FastAPI (port 8000) → Gemini Agent → SSE → MCP Server (port 8001) → Tools
```

**Benefits of SSE Transport:**
- ✅ HTTP-based (no stdio complexity)
- ✅ Remote server support
- ✅ Easy debugging
- ✅ Scalable architecture

## Quick Start

### 1. Setup

```bash
# Navigate to Session 4
cd "Session 4"

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Run

**Option A: Automatic (Recommended)**

```bash
# Windows
start.bat

# Linux/Mac
bash start.sh
```

This automatically starts both MCP server and Agent API.

**Option B: Manual (Two Terminals)**

Terminal 1 - MCP Server:
```bash
python run_mcp_server.py
```

Terminal 2 - Agent API:
```bash
python run_agent_api.py
```

### 3. Test

```bash
# Interactive client
python test_client.py

# Example scripts
python examples.py

# API call
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d "{\"message\":\"Hello!\"}"
```

## Project Structure

```
Session 4/
├── gemini_agent/              # Gemini AI Agent
│   ├── agent.py              # Core agent logic
│   └── api_server.py         # FastAPI wrapper
│
├── mcp_server/               # FastMCP Tool Server
│   ├── server.py            # Main server
│   └── tools/               # Tool implementations
│       ├── search_tool.py   # Web search
│       ├── file_tools.py    # File operations
│       ├── weather_tool.py  # Weather API
│       └── satellite_tool.py # Satellite images
│
├── run_agent_api.py         # Start API server
├── run_mcp_server.py        # Start MCP server
├── test_client.py           # Interactive test client
├── examples.py              # Usage examples
│
├── requirements.txt         # Dependencies
├── .env.example            # Environment template
│
├── AI_AGENT_README.md      # Full documentation
├── QUICKSTART.md           # Quick start guide
├── PROJECT_STRUCTURE.md    # Architecture details
└── README.md               # This file
```

## Features

### Tools Available
- ✅ Web Search (DuckDuckGo)
- ✅ File Read/Write (CSV, TXT, Excel, JPG, JPEG)
- ✅ Weather Information (OpenWeatherMap)
- ✅ Satellite Images (Google Maps/Mapbox)
- ✅ Interactive Dashboard (Prefab UI)

### Agent Capabilities
- ✅ Gemini 3.1 Flash Lite Preview model
- ✅ Automatic tool calling
- ✅ Conversation history
- ✅ Multi-turn dialogues
- ✅ Function calling with MCP

### Agent API Endpoints (Port 8000)
- `GET /` - Health check
- `POST /chat` - Send message to agent
- `POST /reset` - Clear conversation history
- `GET /tools` - List available MCP tools

### MCP Server (Port 8001)
- Runs with SSE transport
- Provides 6 tools to the agent
- Accessible at `http://localhost:8001/sse`

## Example Usage

```python
import requests

# Chat with agent
response = requests.post(
    "http://localhost:8000/chat",
    json={"message": "What's the weather in Paris?"}
)
print(response.json())
```

## Documentation

- **AI_AGENT_README.md** - Complete documentation
- **QUICKSTART.md** - 5-minute setup guide
- **PROJECT_STRUCTURE.md** - Architecture overview

## Configuration

Minimum required in `.env`:
```
GEMINI_API_KEY=your_key_here
```

Optional for full features:
```
OPENWEATHER_API_KEY=your_key
GOOGLE_MAPS_API_KEY=your_key
MAPBOX_ACCESS_TOKEN=your_token
```

## Support

Check the troubleshooting section in AI_AGENT_README.md for common issues.

## License

MIT License
