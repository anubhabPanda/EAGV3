"""CORS proxy for MCP server to enable browser access."""
import asyncio
from aiohttp import web, ClientSession

MCP_SERVER = "http://127.0.0.1:8000"
PROXY_PORT = 8001

async def proxy_handler(request):
    """Proxy all requests to MCP server with CORS headers."""
    path = request.match_info.get('path', '')
    url = f"{MCP_SERVER}/{path}"
    
    async with ClientSession() as session:
        # Forward the request
        async with session.request(
            method=request.method,
            url=url,
            headers={k: v for k, v in request.headers.items() 
                    if k.lower() not in ['host', 'connection']},
            data=await request.read()
        ) as resp:
            # Read response
            body = await resp.read()
            
            # Create response with CORS headers
            response = web.Response(
                body=body,
                status=resp.status,
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                    'Access-Control-Allow-Headers': '*',
                    'Content-Type': resp.headers.get('Content-Type', 'application/json'),
                }
            )
            
            # Copy important headers
            for key in ['Content-Type', 'Transfer-Encoding']:
                if key in resp.headers:
                    response.headers[key] = resp.headers[key]
            
            return response

async def options_handler(request):
    """Handle OPTIONS preflight requests."""
    return web.Response(
        headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': '*',
        }
    )

app = web.Application()
app.router.add_route('OPTIONS', '/{path:.*}', options_handler)
app.router.add_route('*', '/{path:.*}', proxy_handler)

if __name__ == '__main__':
    print(f"CORS Proxy running on http://localhost:{PROXY_PORT}")
    print(f"Proxying to {MCP_SERVER}")
    web.run_app(app, host='127.0.0.1', port=PROXY_PORT)
