"""CLI Agent with Dynamic Prefab Dashboard."""
import asyncio
import os
import sys
import json
import subprocess
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from gemini_agent.agent import GeminiAgent
from mcp import ClientSession
from mcp.client.sse import sse_client

HERE = Path(__file__).parent
DASHBOARD_FILE = HERE / "dashboard_live.py"
LOG_FILE = HERE / "dashboard.log"


DASHBOARD_PROMPT = """Based on the user's request and any tool results, create a Prefab dashboard spec.

Return a JSON with this structure:
{{
  "title": "<dashboard title>",
  "widgets": [
    {{"kind": "stat", "label": "Label", "value": "123", "sub": "optional subtitle"}},
    {{"kind": "badges", "items": [{{"label": "Status", "variant": "success"}}]}},
    {{"kind": "table", "title": "Data", "columns": ["Col1", "Col2"], "rows": [["v1", "v2"]]}},
    {{"kind": "bar", "title": "Chart", "data": [{{"x": "A", "y": 10}}], "x_key": "x", "y_keys": ["y"]}},
    {{"kind": "pie", "title": "Pie", "data": [{{"name": "A", "value": 10}}]}},
    {{"kind": "text", "heading": "Title", "body": "Description"}}
  ]
}}

Available widget kinds: stat, badges, table, bar, pie, line, ring, progress_list, text, checklist, sparkline

User request: {request}
Tool results: {tool_results}
"""


def widget_to_code(w: dict, indent: int = 4) -> str:
    kind = w.get("kind", "")
    ind = " " * indent
    ind2 = " " * (indent + 4)

    if kind == "stat":
        lines = [
            f"{ind}with Column(gap=1):",
            f"{ind2}Muted({w.get('label', '')!r})",
            f"{ind2}H1({w.get('value', '')!r})",
        ]
        if w.get("sub"):
            lines.append(f"{ind2}Muted({w['sub']!r})")
        return "\n".join(lines)

    if kind == "badges":
        lines = [f"{ind}with Row(gap=2):"]
        for item in w.get("items", []):
            lbl = item.get("label", "") if isinstance(item, dict) else str(item)
            var = item.get("variant", "default") if isinstance(item, dict) else "default"
            lines.append(f"{ind2}Badge({lbl!r}, variant={var!r})")
        return "\n".join(lines)

    if kind == "table":
        lines = [f"{ind}with Column(gap=2):"]
        if w.get("title"):
            lines.append(f"{ind2}H3({w['title']!r})")
        cols = w.get("columns", [])
        rows = w.get("rows", [])
        lines.append(f"{ind2}with Row(gap=3):")
        for col in cols:
            lines.append(f"{ind2}    Text({str(col)!r})")
        for row in rows:
            lines.append(f"{ind2}with Row(gap=3):")
            cells = row if isinstance(row, list) else [row.get(c, "") for c in cols]
            for cell in cells:
                lines.append(f"{ind2}    Text({str(cell)!r})")
        return "\n".join(lines)

    if kind == "bar":
        data = w.get("data", [])
        x_key = w.get("x_key", "x")
        y_keys = w.get("y_keys", ["y"])
        if isinstance(y_keys, str):
            y_keys = [y_keys]
        series = ", ".join(f'ChartSeries(data_key={yk!r}, label={yk!r})' for yk in y_keys)
        lines = [f"{ind}with Column(gap=2):"]
        if w.get("title"):
            lines.append(f"{ind2}H3({w['title']!r})")
        lines.append(f"{ind2}BarChart(data={data!r}, series=[{series}], x_axis={x_key!r})")
        return "\n".join(lines)

    if kind == "pie":
        lines = [f"{ind}with Column(gap=2):"]
        if w.get("title"):
            lines.append(f"{ind2}H3({w['title']!r})")
        data = w.get("data", [])
        lines.append(f"{ind2}PieChart(data={data!r}, data_key='value', name_key='name', show_legend=True)")
        return "\n".join(lines)

    if kind == "text":
        lines = [f"{ind}with Column(gap=1):"]
        if w.get("heading"):
            lines.append(f"{ind2}H3({w['heading']!r})")
        if w.get("body"):
            lines.append(f"{ind2}Text({w['body']!r})")
        return "\n".join(lines)

    return f"{ind}Muted('Unsupported widget: {kind}')"


def generate_dashboard(spec: dict) -> str:
    title = spec.get("title", "Dashboard")
    widgets = spec.get("widgets", [])

    widget_code = "\n\n".join(widget_to_code(w, indent=16) for w in widgets)

    return f"""from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge, Card, CardContent, CardHeader, CardTitle,
    Checkbox, Column, H1, H2, H3, Muted, Progress, Ring, Row, Text
)
from prefab_ui.components.charts import BarChart, ChartSeries, LineChart, PieChart, Sparkline

with PrefabApp(css_class="max-w-5xl mx-auto p-6") as app:
    with Card():
        with CardHeader():
            CardTitle({title!r})
        with CardContent():
            with Column(gap=4):
{widget_code}
"""


async def main():
    print("Connecting to MCP server...")
    sse_context = sse_client("http://localhost:8001/sse")
    read, write = await sse_context.__aenter__()
    mcp_session = ClientSession(read, write)
    await mcp_session.__aenter__()
    await mcp_session.initialize()
    
    agent = GeminiAgent(mcp_client=mcp_session)
    
    # Start dashboard server
    DASHBOARD_FILE.write_text(generate_dashboard({"title": "Waiting for query..."}))
    LOG_FILE.write_text("")
    log_f = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        ["prefab", "serve", "dashboard_live.py"],
        cwd=HERE,
        stdout=log_f,
        stderr=subprocess.STDOUT
    )
    time.sleep(1.5)
    print("\nDashboard running at http://localhost:5175\n")
    
    try:
        while True:
            query = input("\nYou: ").strip()
            if not query or query.lower() in {"quit", "exit"}:
                break
            
            response = await agent.chat(query, max_iterations=10)
            print(f"\nAgent: {response['text']}\n")
            
            # Generate dashboard if tools were called
            if response.get('tool_calls'):
                tool_results = {tc['tool']: tc['result'] for tc in response['tool_calls']}
                prompt = DASHBOARD_PROMPT.format(request=query, tool_results=json.dumps(tool_results, indent=2))
                
                from google import genai
                client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                dash_resp = client.models.generate_content(
                    model="gemini-3.1-flash-lite-preview",
                    contents=prompt
                )
                spec_text = dash_resp.text.strip()
                if spec_text.startswith("```"):
                    spec_text = spec_text.strip("`").split("\n", 1)[1].rsplit("\n", 1)[0]
                
                spec = json.loads(spec_text)
                code = generate_dashboard(spec)
                DASHBOARD_FILE.write_text(code)
                proc.terminate()
                proc.wait()
                proc = subprocess.Popen(
                    ["prefab", "serve", "dashboard_live.py"],
                    cwd=HERE,
                    stdout=log_f,
                    stderr=subprocess.STDOUT
                )
                time.sleep(1)
                print("→ Dashboard updated")
                
    finally:
        proc.terminate()
        proc.wait()
        log_f.close()
        await mcp_session.__aexit__(None, None, None)
        await sse_context.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
