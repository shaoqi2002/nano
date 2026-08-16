from pydantic import BaseModel


class BalanceInfo(BaseModel):
    currency: str
    total_balance: str
    granted_balance: str
    topped_up_balance: str


class DeepSeekBalanceResponse(BaseModel):
    is_available: bool
    balance_infos: list[BalanceInfo]
