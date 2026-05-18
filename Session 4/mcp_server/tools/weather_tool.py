"""Weather information tool using OpenWeatherMap API."""
import os
import aiohttp
from typing import Dict, Any


async def get_weather(location: str, units: str = "metric") -> Dict[str, Any]:
    """
    Get current weather information for a location.
    
    Args:
        location: City name or coordinates (lat,lon)
        units: Temperature units (metric, imperial, standard)
        
    Returns:
        Weather data dictionary
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    
    if not api_key:
        return {"error": "OPENWEATHER_API_KEY not configured"}
    
    try:
        base_url = "https://api.openweathermap.org/data/2.5/weather"
        
        params = {
            "q": location,
            "appid": api_key,
            "units": units
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    return {
                        "location": data.get("name", location),
                        "country": data.get("sys", {}).get("country", ""),
                        "temperature": data.get("main", {}).get("temp"),
                        "feels_like": data.get("main", {}).get("feels_like"),
                        "humidity": data.get("main", {}).get("humidity"),
                        "pressure": data.get("main", {}).get("pressure"),
                        "description": data.get("weather", [{}])[0].get("description", ""),
                        "wind_speed": data.get("wind", {}).get("speed"),
                        "clouds": data.get("clouds", {}).get("all"),
                        "units": units,
                        "coordinates": {
                            "lat": data.get("coord", {}).get("lat"),
                            "lon": data.get("coord", {}).get("lon")
                        }
                    }
                else:
                    error_data = await response.json()
                    return {"error": f"Weather API error: {error_data.get('message', 'Unknown error')}"}
                    
    except Exception as e:
        return {"error": f"Failed to fetch weather: {str(e)}"}
