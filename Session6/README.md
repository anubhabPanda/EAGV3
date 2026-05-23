# Agent with MDAP architecture

A modular, production-ready goal-oriented agent with MCP tool integration, intelligent memory management, and comprehensive tracing. Only tool calling agent can't handle user queries with multiple objectives. So, this agent breaks it down into various components - Memory, Perception, Decision and Action. Perception plans - break down goals and passes one goal at a time to Decision. Decision calls the tools. Clear separation of boundaries and roles with Pydantic contracts.

---

## Architecture Overview

```
┌─────────────┐
│   Agent     │ - Main orchestration loop
└──────┬──────┘
       │
       ├──> Perception    - Goal decomposition & tracking
       ├──> Memory        - LLM-powered memory with deduplication
       ├──> Decision      - Tool selection & answer generation
       ├──> Action        - MCP tool execution & artifact management
       └──> Tracer        - Formatted logging (terminal + file)
```

---

## Key Features

### 1. **Goal-Oriented Reasoning**
- Perception decomposes queries into bounded goals
- Tracks goal completion state across iterations
- Generates final answer when all goals complete

### 2. **Intelligent Memory System**
- **LLM-powered classification**: Gemini auto-classifies into fact/preference/tool_outcome/scratchpad
- **O(1) deduplication**: Hash-based index prevents duplicate storage
- **Keyword overlap search**: Fast retrieval with Counter-based ranking
- **Persistent storage**: JSON file at `state/memory.json`

### 3. **MCP Tool Integration**
- **9 tools**: web_search, fetch_url, get_time, currency_convert, read_file, list_dir, create_file, update_file, edit_file
- **HTTP transport**: Runs MCP server as independent process (required for browser automation)
- **Artifact storage**: Large outputs (>4KB) stored as artifacts with IDs like `art:1`

### 4. **Production Features**
- **Interactive mode**: Continuous loop until `exit`/`quit`
- **Comprehensive logging**: Dual output (terminal + file in `logs/`)
- **Error handling**: 3 retries on all LLM calls
- **Timeout protection**: 120s timeout on MCP tool calls
- **Detailed tracing**: Memory hits, goal state, tool calls, action results

---

## Quick Start

### Prerequisites
1. **LLM Gateway V3** running on port 8101
2. **MCP Server** (HTTP mode for fetch_url to work)

### Option 1: stdio Transport (Default)
```bash
cd Session6
python agent.py
```
**Note**: `fetch_url` will NOT work in stdio mode (see Known Issues)

### Option 2: HTTP Transport (Recommended)
**Terminal 1 - Start MCP Server:**
```bash
cd Session6
python mcp_server.py
```

**Terminal 2 - Start Agent:**
```bash
cd Session6
set MCP_TRANSPORT=http
python agent.py
```

### Interactive Usage
```
👤 You: Find 3 family-friendly things to do in Tokyo this weekend

[memory.remember]  classified "Find 3 family-friendly things to do..." as scratchpad
                   keywords: ["tokyo", "family-friendly", "weekend"]

─── iter 1 ───
[memory.read]    retrieved 1 memory hit
                 keywords: ["tokyo", "family-friendly", "weekend"]
[perception]    →[open] Goal 1: Find 3 family-friendly activities in Tokyo
                 [open] Goal 2: Check weekend weather forecast
[decision]      TOOL_CALL: web_search({"query":"family-friendly Tokyo"})
[action]        → ok
                The best Tokyo Family-friendly activities 2025...

─── iter 2 ───
...

─── FINAL ANSWER ───
For a family-friendly weekend in Tokyo, I recommend...

👤 You: exit
```

---

## Critical Issues Resolved

### Issue 1: crawl4ai Hanging in stdio Transport

**Problem:**
- `fetch_url` tool hung for 120s timeout when using stdio transport
- crawl4ai's Playwright browser automation incompatible with MCP stdio subprocess
- File descriptor redirection (`os.dup2`) broke stdio protocol channel

**Root Cause:**
```
Agent Process
  └─> MCP Server (subprocess via stdio)
        └─> stdout = JSON-RPC protocol channel
        └─> crawl4ai → Playwright → Browser
              └─> Writes to stdout → CORRUPTS PROTOCOL → DEADLOCK
```

**Solution:**
- **Switched to HTTP transport** for MCP server
- Server runs as independent process, stdout no longer protocol channel
- Browser automation works cleanly without stdio conflicts

**Files Modified:**
- `mcp_server.py`: Added HTTP transport support
- `agent.py`: Added `MCP_TRANSPORT` env var detection
- See `HTTP_TRANSPORT_SETUP.md` for details

---

### Issue 2: Memory Deduplication

**Problem:**
- Same content stored multiple times
- Linear O(n) duplicate checking was slow

**Solution:**
- Hash-based `_text_index` for O(1) duplicate detection
- Deduplication on `raw_text` field
- See `MEMORY_DEDUPLICATION.md`

---

### Issue 3: Agent Loop & Final Answer

**Evolution:**
1. **v1**: Decision generated final answer
2. **v2**: Perception generates final answer (centralized completion logic)

**Current Behavior:**
- Perception tracks all goals
- When all goals `done: true`, Perception synthesizes final answer
- Agent exits with final answer

---

### Issue 4: Prompt Engineering

**Key Improvements:**
- **Perception**: Added self-checks, reasoning types, artifact attachment rules
- **Decision**: 3-part substantive answer rule, no meta-commentary
- **Memory**: Structured extraction with MemoryExtraction schema

**See individual service files for full prompts**

---

## File Structure

```
Session6/
├── agent.py                 # Main orchestration loop
├── mcp_server.py           # MCP server with 9 tools
├── schemas.py              # Pydantic models
├── tracer.py               # Formatted logging
├── utils.py                # LLM gateway health check
│
├── services/
│   ├── perception_service.py   # Goal decomposition & tracking
│   ├── memory_service.py       # LLM-powered memory
│   ├── decision_service.py     # Tool selection & answers
│   ├── action_service.py       # MCP tool execution
│   └── artifact_service.py     # Large output storage
│
├── state/
│   ├── memory.json         # Persistent memory storage
│   └── artifacts/          # Artifact files
│
├── logs/                   # Agent run logs
├── sandbox/                # Sandboxed file operations
│
└── *.md                    # Documentation
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | Transport mode: `stdio` or `http` |
| `MCP_HTTP_URL` | `http://127.0.0.1:8000/mcp` | MCP server URL (HTTP mode) |

---

## Known Issues & Workarounds

### 1. fetch_url Doesn't Work in stdio Mode
**Issue**: crawl4ai + Playwright incompatible with stdio subprocess  
**Workaround**: Use HTTP transport (see Quick Start Option 2)  
**Status**: Won't fix - architectural limitation

### 2. First fetch_url Slow (~15s)
**Issue**: Browser initialization takes 10-15s on first call  
**Workaround**: Expected behavior, subsequent calls faster  
**Future**: Persistent browser (incompatible with current MCP setup)

### 3. Playwright Browsers Not Installed
**Issue**: `Executable doesn't exist` error on fetch_url  
**Fix**: `playwright install chromium`  
**See**: `PLAYWRIGHT_SETUP_FIX.md`

---

## Debugging

### VS Code Launch Configurations
Root `.vscode/launch.json` contains:
1. **Session6: Agent - stdio** - Default mode
2. **Session6: Agent - HTTP** - HTTP transport mode
3. **Session6: MCP Server** - Debug MCP server
4. **Session6: Test fetch_url** - Test fetch_url tool

### Log Analysis
```bash
# View latest run
cat logs/agent_*.log | tail -100

# Search for errors
grep ERROR logs/agent_*.log

# Find MCP tool logs
grep "MCP-TOOL" logs/agent_*.log
```

---

## Performance Notes

- **LLM Calls**: 3 retry attempts on all `llm.chat()` calls
- **MCP Timeout**: 120s per tool call
- **Memory Dedup**: O(1) hash lookup
- **Artifact Threshold**: 4KB (responses >4KB stored as artifacts)

---

## Future Improvements

1. **Persistent browser** for fetch_url (requires different architecture)
2. **Parallel tool execution** (currently sequential)
3. **Streaming LLM responses** (currently blocking)
4. **Memory pruning** (auto-cleanup old/irrelevant memories)

---

## 4 Queries and Terminal Logs

### Query A. Shannon Wikipedia (artifact attach test)

```
Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his
birth date, death date, and three key contributions to information
theory.
```
### Query B. Tokyo activities with weather constraint (multi-goal plus memory carryover)

```
Find 3 family-friendly things to do in Tokyo this weekend.
Check Saturday's weather forecast there and tell me which one
is most appropriate.
```
### Query C. Mom's birthday (durable memory across two runs)

```
Run 1: My mom's birthday is 15 May 2026. Remember that and give me
       a calendar reminder for two weeks before and on the day.

Run 2: When is mom's birthday?
```

### Query D. Asyncio research (multi-source synthesis)

```
Search for 'Python asyncio best practices', read the top 3 results,
and give me a short numbered list of the advice they agree on.
```

## Prompt Evaluation

