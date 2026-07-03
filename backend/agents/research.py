"""
Web Research helper — pulls live data from the whole web via Tavily.
Used by the Lead Generator to find real business prospects for any industry.
"""
from tavily import TavilyClient
from config import settings

_tavily = None


def get_tavily() -> TavilyClient:
    global _tavily
    if _tavily is None:
        _tavily = TavilyClient(api_key=settings.tavily_api_key)
    return _tavily


async def search_market(query: str, max_results: int = 5, domains: list = None) -> list[dict]:
    """Search the whole web for business/lead data.
    `domains`: pass a specific include-domains list to narrow the search. Default (None or [])
    searches the entire web, so lead hunts work for any industry."""
    try:
        client = get_tavily()
        kwargs = {"query": query, "search_depth": "advanced", "max_results": max_results}
        if domains:
            kwargs["include_domains"] = domains
        results = client.search(**kwargs)
        return results.get("results", [])
    except Exception as e:
        return [{"error": str(e)}]
