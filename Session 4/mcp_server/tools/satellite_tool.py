"""Satellite image tool using various satellite image APIs."""
import os
import aiohttp
import base64
from typing import Dict, Any


async def get_satellite_image(lat: float, lon: float, zoom: int = 13, width: int = 640, height: int = 640) -> Dict[str, Any]:
    """
    Get satellite image for given coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
        zoom: Zoom level (1-20, default 13)
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        Dictionary with base64 encoded satellite image
    """
    # Using Google Maps Static API (requires API key)
    # Alternative: Mapbox, OpenStreetMap, etc.
    
    google_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN")
    
    try:
        if google_api_key:
            # Google Maps Static API
            url = "https://maps.googleapis.com/maps/api/staticmap"
            params = {
                "center": f"{lat},{lon}",
                "zoom": zoom,
                "size": f"{width}x{height}",
                "maptype": "satellite",
                "key": google_api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        base64_image = base64.b64encode(image_data).decode()
                        
                        return {
                            "type": "satellite_image",
                            "coordinates": {"lat": lat, "lon": lon},
                            "zoom": zoom,
                            "size": {"width": width, "height": height},
                            "base64": base64_image,
                            "provider": "google_maps"
                        }
                    else:
                        return {"error": f"Google Maps API error: {response.status}"}
        
        elif mapbox_token:
            # Mapbox Static Images API
            # Format: https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom}/{width}x{height}
            url = f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom}/{width}x{height}"
            params = {"access_token": mapbox_token}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        base64_image = base64.b64encode(image_data).decode()
                        
                        return {
                            "type": "satellite_image",
                            "coordinates": {"lat": lat, "lon": lon},
                            "zoom": zoom,
                            "size": {"width": width, "height": height},
                            "base64": base64_image,
                            "provider": "mapbox"
                        }
                    else:
                        return {"error": f"Mapbox API error: {response.status}"}
        
        else:
            # Fallback to OpenStreetMap (no satellite, but free)
            return {
                "error": "No satellite image API configured. Please set GOOGLE_MAPS_API_KEY or MAPBOX_ACCESS_TOKEN",
                "fallback": f"OpenStreetMap URL: https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"
            }
            
    except Exception as e:
        return {"error": f"Failed to fetch satellite image: {str(e)}"}
