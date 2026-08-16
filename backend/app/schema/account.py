from pydantic import BaseModel


class BalanceInfo(BaseModel):
    currency: str
    total_balance: str
    granted_balance: str
    topped_up_balance: str


class DeepSeekBalanceResponse(BaseModel):
    is_available: bool
    balance_infos: list[BalanceInfo]


class TavilyKeyUsage(BaseModel):
    usage: int
    limit: int
    search_usage: int = 0
    extract_usage: int = 0
    crawl_usage: int = 0
    map_usage: int = 0
    research_usage: int = 0


class TavilyAccountUsage(BaseModel):
    current_plan: str
    plan_usage: int
    plan_limit: int
    paygo_usage: int = 0
    paygo_limit: int = 0
    search_usage: int = 0
    extract_usage: int = 0
    crawl_usage: int = 0
    map_usage: int = 0
    research_usage: int = 0


class TavilyUsageResponse(BaseModel):
    key: TavilyKeyUsage
    account: TavilyAccountUsage
