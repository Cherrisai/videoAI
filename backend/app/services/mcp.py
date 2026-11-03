"""Small MCP tool client boundary. Only tools exposed by configured servers can be called."""
import json
import logging
from contextlib import AsyncExitStack
from urllib.parse import urlsplit
from app.core.config import get_settings

log = logging.getLogger(__name__)


def infer_lookup_kind(question: str) -> str | None:
    """Route explicit external lookup requests to a search type without another LLM round-trip.

    The language model still reasons over the returned sources for the answer; this
    lightweight router keeps ordinary video chat fast and only calls tools on intent.
    """
    lowered = question.lower()
    candidate_url = next((part.strip(".,;()[]") for part in question.split() if part.startswith(("https://", "http://"))), "")
    if candidate_url:
        host = (urlsplit(candidate_url).hostname or "").lower().removeprefix("www.")
        if any(host == domain or host.endswith("." + domain) for domain in (
            "myntra.com", "amazon.com", "amazon.in", "flipkart.com", "etsy.com", "ebay.com", "ajio.com",
        )):
            return "product"
        if any(host == domain or host.endswith("." + domain) for domain in (
            "youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "dailymotion.com",
        )):
            return "video"
        if urlsplit(candidate_url).path.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
            return "video"
    asks_external = any(term in lowered for term in (
        "search", "look up", "find", "show", "link", "links", "website", "online",
        "internet", "source", "where can i", "recommend", "similar to", "buy", "purchase",
    ))
    if not asks_external:
        return None

    video_terms = ("video link", "direct video", "find the video", "source video", "watch link", "video source", "clip link", "video similar")
    if any(term in lowered for term in video_terms):
        return "video"

    product_terms = (
        "product", "buy", "purchase", "shop", "shopping", "price", "jacket", "shirt",
        "dress", "shoes", "sneaker", "bag", "watch", "phone", "laptop", "brand",
        "clothing", "item link", "this item", "this thing", "who sells", "product link", "outfit",
    )
    if any(term in lowered for term in product_terms):
        return "product"

    image_terms = ("image", "images", "photo", "picture", "pictures")
    if any(term in lowered for term in image_terms):
        return "image"

    place_terms = ("near me", "nearby", "in my area", "location", "restaurant", "where is", "find places", "places to", "place to", "directions", "physical store")
    if any(term in lowered for term in place_terms):
        return "place"

    return "web"


class MCPTools:
    async def list_tools(self) -> list[dict]:
        configured = self._config()
        if not configured:
            return []
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            return []
        result = []
        async with AsyncExitStack() as stack:
            for server in configured:
                if server.get("transport") != "stdio" or not server.get("command"):
                    continue
                params = StdioServerParameters(command=server["command"], args=server.get("args", []), env=server.get("env", {}))
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools = await session.list_tools()
                result.extend({"server": server["name"], "name": tool.name, "description": tool.description or ""} for tool in tools.tools)
        return result

    async def lookup(self, query: str, requested: str) -> list[dict]:
        """Invoke only server/name pairs explicitly included in allow_tools."""
        configured = self._config()
        if not configured:
            return []
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            return []
        results = []
        async with AsyncExitStack() as stack:
            for server in configured:
                if server.get("transport") != "stdio" or not server.get("command"):
                    continue
                allowed = set(server.get("allow_tools", []))
                aliases = {
                    "web": ("web_search",),
                    "place": ("local_search", "place_search"),
                    "image": ("image_search",),
                    "video": ("video_search",),
                    "product": ("product_search",),
                }.get(requested, (requested,))
                matches = [name for name in allowed if any(alias in name.lower() for alias in aliases)]
                # Brave has no dedicated product catalog tool. For product
                # questions, use an explicitly allowed web-search tool to find
                # candidate product pages; the chat prompt labels them as likely matches.
                if requested == "product" and not matches:
                    matches = [name for name in allowed if "web_search" in name.lower()]
                # A general web search is a useful fallback when a server lacks a
                # dedicated video tool; returned pages remain source links, not
                # promises that the app can download or play third-party content.
                if requested == "video" and not matches:
                    matches = [name for name in allowed if "web_search" in name.lower()]
                if not matches:
                    continue
                params = StdioServerParameters(command=server["command"], args=server.get("args", []), env=server.get("env", {}))
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                available = {tool.name: tool for tool in (await session.list_tools()).tools}
                for name in matches:
                    tool = available.get(name)
                    if not tool:
                        continue
                    properties = (tool.inputSchema or {}).get("properties", {})
                    arguments = {key: query[:400] for key in ("query", "q") if key in properties}
                    if not arguments:
                        log.warning("Configured MCP tool %s has no supported query parameter", name)
                        continue
                    result = await session.call_tool(name, arguments)
                    for item in result.content:
                        if getattr(item, "text", None):
                            results.append({"server": server["name"], "tool": name, "text": item.text[:3000]})
        return results

    def _config(self) -> list[dict]:
        try:
            value = json.loads(get_settings().mcp_servers_json)
            configured = value if isinstance(value, list) else []
        except (ValueError, TypeError):
            log.warning("MCP_SERVERS_JSON is invalid")
            configured = []

        # The optional Brave adapter is a real MCP stdio server. Keeping its key in
        # the environment avoids asking users to embed secrets inside JSON config.
        settings = get_settings()
        if settings.brave_api_key and not any(server.get("name") == "brave-search" for server in configured):
            configured.append({
                "name": "brave-search",
                "transport": "stdio",
                # Run the package entry file directly. Copying npm's generated
                # bin shim into a different image path breaks its relative imports.
                "command": "/usr/local/bin/node",
                "args": ["/usr/local/lib/node_modules/@brave/brave-search-mcp-server/dist/index.js"],
                "env": {"BRAVE_API_KEY": settings.brave_api_key},
                "allow_tools": ["brave_web_search", "brave_local_search", "brave_place_search", "brave_image_search", "brave_video_search"],
            })
        return configured
