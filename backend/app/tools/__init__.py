from langchain_core.tools import BaseTool

from app.tools.deep_research import create_deep_research_tool
from app.tools.webextract import create_web_extract_tool
from app.tools.websearch import create_web_search_tool
from app.tools.local_read import create_local_read_tools
from app.tools.local_write import create_local_write_tools
from app.tooling import ToolRegistry, ToolSpec


def create_tool_registry(tavily_api_key: str | None) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in create_local_read_tools():
        registry.register(ToolSpec(
            name=tool.name,
            version="1.0.0",
            tool=tool,
            category="local",
            timeout_seconds=10.0,
            allowed_agents=frozenset({"chat_agent"}),
            tags=frozenset({"local", "readonly"}),
        ))
    for tool in create_local_write_tools():
        registry.register(ToolSpec(
            name=tool.name,
            version="1.0.0",
            tool=tool,
            category="documents" if tool.name.startswith("word_") else "local",
            risk_level="write",
            side_effect=True,
            idempotent=False,
            timeout_seconds=180.0 if tool.name.startswith("word_") else 10.0,
            allowed_agents=frozenset({"chat_agent"}),
            tags=frozenset({"local", "write"}),
        ))
    if not tavily_api_key or not tavily_api_key.strip():
        return registry
    web_roles = frozenset({"chat_agent", "web_researcher", "general_researcher"})
    for tool, timeout, retries in (
        (create_web_search_tool(tavily_api_key), 20.0, 1),
        (create_web_extract_tool(tavily_api_key), 50.0, 0),
        (create_deep_research_tool(tavily_api_key), 210.0, 0),
    ):
        registry.register(ToolSpec(
            name=tool.name,
            version="1.0.0",
            tool=tool,
            category="web",
            timeout_seconds=timeout,
            max_retries=retries,
            allowed_agents=web_roles,
            tags=frozenset({"network", "readonly"}),
        ))
    return registry


def create_tools(tavily_api_key: str | None) -> list[BaseTool]:
    """Compatibility helper for callers that only need LangChain tools."""
    return create_tool_registry(tavily_api_key).langchain_tools()


__all__ = ["create_tool_registry", "create_tools"]
