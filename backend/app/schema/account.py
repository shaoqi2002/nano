from pydantic import BaseModel, field_validator


class BalanceInfo(BaseModel):
    currency: str
    total_balance: str
    granted_balance: str
    topped_up_balance: str


class DeepSeekBalanceResponse(BaseModel):
    is_available: bool
    balance_infos: list[BalanceInfo]


class TavilyKeyUsage(BaseModel):
    usage: int = 0
    limit: int = 0
    search_usage: int = 0
    extract_usage: int = 0
    crawl_usage: int = 0
    map_usage: int = 0
    research_usage: int = 0

    @field_validator(
        "usage", "limit", "search_usage", "extract_usage", "crawl_usage",
        "map_usage", "research_usage", mode="before",
    )
    @classmethod
    def normalize_usage(cls, value: object) -> int:
        if value in (None, ""):
            return 0
        return int(float(value))


class TavilyAccountUsage(BaseModel):
    current_plan: str = "Unknown"
    plan_usage: int = 0
    plan_limit: int = 0
    paygo_usage: int = 0
    paygo_limit: int = 0
    search_usage: int = 0
    extract_usage: int = 0
    crawl_usage: int = 0
    map_usage: int = 0
    research_usage: int = 0

    @field_validator("current_plan", mode="before")
    @classmethod
    def normalize_plan(cls, value: object) -> str:
        return str(value) if value not in (None, "") else "Unknown"

    @field_validator(
        "plan_usage", "plan_limit", "paygo_usage", "paygo_limit",
        "search_usage", "extract_usage", "crawl_usage", "map_usage",
        "research_usage", mode="before",
    )
    @classmethod
    def normalize_usage(cls, value: object) -> int:
        if value in (None, ""):
            return 0
        return int(float(value))


class TavilyUsageResponse(BaseModel):
    key: TavilyKeyUsage
    account: TavilyAccountUsage


class EmbeddingStatusResponse(BaseModel):
    configured: bool
    model: str
    dimensions: int
