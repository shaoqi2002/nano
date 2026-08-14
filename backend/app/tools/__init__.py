from langchain_core.tools import BaseTool

from app.tools.deep_research import create_deep_research_tool
from app.tools.webextract import create_web_extract_tool
from app.tools.websearch import create_web_search_tool


def create_tools(tavily_api_key: str | None) -> list[BaseTool]:
    if not tavily_api_key or not tavily_api_key.strip():
        return []
    return [
        create_web_search_tool(tavily_api_key),
        create_web_extract_tool(tavily_api_key),
        create_deep_research_tool(tavily_api_key),
    ]


__all__ = ["create_tools"]
