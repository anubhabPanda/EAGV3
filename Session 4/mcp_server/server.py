"""FastMCP Server with multiple tools."""
import os
import sys
from typing import Dict, Any, List
from pathlib import Path

# Add parent directory to path for imports to work when run directly
# This allows both relative and absolute imports to work
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Heading, Text, Card, CardTitle, CardContent,
    Column, Row, Image, Button
)
from prefab_ui.components.control_flow import ForEach, If
from prefab_ui.actions import SetState, ShowToast
from prefab_ui.actions.mcp import CallTool
from prefab_ui.rx import Rx, RESULT

# Import tools - use try/except to handle both relative and absolute imports
try:
    from .tools.search_tool import web_search
    from .tools.file_tools import read_local_file, write_local_file
    from .tools.weather_tool import get_weather
    from .tools.satellite_tool import get_satellite_image
except ImportError:
    # Fall back to absolute imports when running directly
    from tools.search_tool import web_search
    from tools.file_tools import read_local_file, write_local_file
    from tools.weather_tool import get_weather
    from tools.satellite_tool import get_satellite_image


# Initialize FastMCP server
mcp = FastMCP("MultiTool Server")


@mcp.tool()
async def search_web(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Search the web for information.
    
    Args:
        query: Search query string
        max_results: Maximum number of results (default 5)
    """
    return await web_search(query, max_results)


@mcp.tool()
def read_file(file_path: str) -> Dict[str, Any]:
    """
    Read local files (csv, txt, excel, jpg, jpeg).
    
    Args:
        file_path: Path to the file to read
    """
    return read_local_file(file_path)


@mcp.tool()
def write_file(file_path: str, content: Any, file_type: str = "txt") -> Dict[str, str]:
    """
    Write content to local files (csv, txt, excel, jpg, jpeg).
    
    Args:
        file_path: Path where to write the file
        content: Content to write
        file_type: Type of file (txt, csv, excel, jpg, jpeg)
    """
    return write_local_file(file_path, content, file_type)


@mcp.tool()
async def get_weather_info(location: str, units: str = "metric") -> Dict[str, Any]:
    """
    Get current weather information for a location.
    
    Args:
        location: City name or coordinates
        units: Temperature units (metric, imperial, standard)
    """
    return await get_weather(location, units)


@mcp.tool()
async def get_satellite_map(lat: float, lon: float, zoom: int = 13) -> Dict[str, Any]:
    """
    Get satellite image for given coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
        zoom: Zoom level (1-20, default 13)
    """
    return await get_satellite_image(lat, lon, zoom)


@mcp.tool()
def dashboard(weather_location: str = "", search_query: str = "", lat: float = 0, lon: float = 0) -> Dict[str, Any]:
    """
    Interactive dashboard showing weather, search results, and satellite images based on provided data.

    Args:
        weather_location: Location for weather info
        search_query: Query for web search
        lat: Latitude for satellite image
        lon: Longitude for satellite image
    """

    with Column(gap=6, css_class="p-6 max-w-6xl mx-auto") as view:
        Heading("Multi-Tool Dashboard", level=1)

        # Show initial data if provided
        if weather_location:
            with Card(css_class="mb-6"):
                CardTitle(f"Weather for {weather_location}")
                with CardContent():
                    Text("Weather data will be fetched...")

        if search_query:
            with Card(css_class="mb-6"):
                CardTitle(f"Search Results for: {search_query}")
                with CardContent():
                    Text("Search results will be displayed...")

        if lat != 0 or lon != 0:
            with Card(css_class="mb-6"):
                CardTitle(f"Satellite Image")
                with CardContent():
                    Text(f"Location: {lat}, {lon}")

        # Weather Section
        with Card(css_class="mb-6"):
            CardTitle("Weather Information")
            with CardContent():
                with Row(gap=4, css_class="items-end mb-4"):
                    with Column(css_class="flex-1"):
                        Text("Location", css_class="text-sm font-medium mb-2")
                        from prefab_ui.components import Input
                        Input(
                            name="location",
                            placeholder="Enter city name...",
                            value=location,
                            on_change=SetState("location", "{{ $event }}")
                        )
                    Button(
                        "Get Weather",
                        on_click=[
                            CallTool(
                                "get_weather_info",
                                arguments={"location": location},
                                on_success=[
                                    SetState("weather_data", RESULT),
                                    ShowToast("Weather data loaded", variant="success")
                                ],
                                on_error=ShowToast("{{ $error }}", variant="error")
                            )
                        ]
                    )

                # Weather Display
                with If("weather_data"):
                    with Column(gap=2, css_class="bg-blue-50 dark:bg-blue-900 p-4 rounded"):
                        Text("📍 {{ weather_data.location }}, {{ weather_data.country }}", css_class="text-lg font-bold")
                        Text("🌡️ Temperature: {{ weather_data.temperature }}° (Feels like {{ weather_data.feels_like }}°)")
                        Text("☁️ {{ weather_data.description }}")
                        Text("💧 Humidity: {{ weather_data.humidity }}%")
                        Text("💨 Wind Speed: {{ weather_data.wind_speed }} m/s")

        # Web Search Section
        with Card(css_class="mb-6"):
            CardTitle("Web Search")
            with CardContent():
                with Row(gap=4, css_class="items-end mb-4"):
                    with Column(css_class="flex-1"):
                        Text("Search Query", css_class="text-sm font-medium mb-2")
                        from prefab_ui.components import Input
                        Input(
                            name="search_query",
                            placeholder="Search the web...",
                            value=search_query,
                            on_change=SetState("search_query", "{{ $event }}")
                        )
                    Button(
                        "Search",
                        on_click=[
                            CallTool(
                                "search_web",
                                arguments={"query": search_query, "max_results": 5},
                                on_success=[
                                    SetState("search_results", RESULT),
                                    ShowToast("Search completed", variant="success")
                                ],
                                on_error=ShowToast("{{ $error }}", variant="error")
                            )
                        ]
                    )

                # Search Results Display
                with If("search_results"):
                    with Column(gap=3, css_class="mt-4"):
                        with ForEach("search_results"):
                            with Card(css_class="bg-gray-50 dark:bg-gray-800"):
                                with CardContent():
                                    Text("{{ title }}", css_class="font-bold text-blue-600 dark:text-blue-400")
                                    Text("{{ snippet }}", css_class="text-sm text-gray-700 dark:text-gray-300 mt-1")
                                    Text("🔗 {{ url }}", css_class="text-xs text-gray-500 mt-1")

        # Satellite Image Section
        with Card(css_class="mb-6"):
            CardTitle("Satellite Image")
            with CardContent():
                with Row(gap=4, css_class="items-end mb-4"):
                    with Column(css_class="flex-1"):
                        with Row(gap=2):
                            with Column(css_class="flex-1"):
                                Text("Latitude", css_class="text-sm font-medium mb-2")
                                from prefab_ui.components import Input
                                Input(
                                    name="lat",
                                    placeholder="Latitude",
                                    value=lat,
                                    on_change=SetState("lat", "{{ $event }}")
                                )
                            with Column(css_class="flex-1"):
                                Text("Longitude", css_class="text-sm font-medium mb-2")
                                Input(
                                    name="lon",
                                    placeholder="Longitude",
                                    value=lon,
                                    on_change=SetState("lon", "{{ $event }}")
                                )
                    Button(
                        "Get Satellite Image",
                        on_click=[
                            CallTool(
                                "get_satellite_map",
                                arguments={"lat": "{{ lat }}", "lon": "{{ lon }}"},
                                on_success=[
                                    SetState("satellite_data", RESULT),
                                    ShowToast("Satellite image loaded", variant="success")
                                ],
                                on_error=ShowToast("{{ $error }}", variant="error")
                            )
                        ]
                    )

                # Satellite Image Display
                with If("satellite_data"):
                    with Column(gap=2, css_class="mt-4"):
                        Text("📍 Location: {{ satellite_data.coordinates.lat }}, {{ satellite_data.coordinates.lon }}", css_class="font-medium")
                        with If("satellite_data.base64"):
                            Image(
                                src="data:image/png;base64,{{ satellite_data.base64 }}",
                                alt="Satellite image",
                                css_class="w-full max-w-2xl rounded-lg shadow-lg"
                            )

    return PrefabApp(
        title="Multi-Tool Dashboard",
        view=view,
        state={
            "location": "",
            "weather_data": None,
            "search_query": "",
            "search_results": None,
            "lat": "",
            "lon": "",
            "satellite_data": None
        }
    )


if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv()

    # Run MCP server with SSE transport
    port = int(os.getenv("MCP_SERVER_PORT", "8001"))

    print("=" * 60)
    print("Starting FastMCP Server with SSE Transport")
    print("=" * 60)
    print(f"Server: http://localhost:{port}")
    print(f"Transport: SSE (Server-Sent Events)")
    print("\nAvailable tools:")
    print("  - search_web")
    print("  - read_file")
    print("  - write_file")
    print("  - get_weather_info")
    print("  - get_satellite_map")
    print("  - dashboard (Prefab UI)")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    # Run with SSE transport
    mcp.run(transport="sse", port=port, host="0.0.0.0")
