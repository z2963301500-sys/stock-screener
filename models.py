from pydantic import BaseModel, Field
from typing import Literal


class TechnicalScreeningRequest(BaseModel):
    strategy: Literal["ma_band", "rsi_extreme", "volume_breakout", "momentum", "reversal", "gap_fade"]
    params: dict[str, float] = Field(default_factory=dict)
    top_n: int = Field(default=50, ge=10, le=200)
    exclude_st: bool = True
    min_market_cap: float = 0


class MultifactorScreeningRequest(BaseModel):
    weight_momentum: float = Field(default=0.30, ge=0, le=1)
    weight_volatility: float = Field(default=0.25, ge=0, le=1)
    weight_volume: float = Field(default=0.25, ge=0, le=1)
    weight_reversion: float = Field(default=0.20, ge=0, le=1)
    top_n: int = Field(default=50, ge=10, le=200)
    exclude_st: bool = True


class ScreeningResult(BaseModel):
    code: str
    name: str
    price: float | None
    score: float
    indicator_value: float | None = None
    pe: float | None = None
    pb: float | None = None
    change_pct: float | None = None
    signal_strength: str = "weak"


class ScreeningResponse(BaseModel):
    results: list[ScreeningResult]
    total_scanned: int
    total_matched: int
    elapsed_ms: float


class StockCandle(BaseModel):
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int = 0


class StockHistoryResponse(BaseModel):
    code: str
    name: str
    candles: list[StockCandle]


class StockIndicatorsResponse(BaseModel):
    code: str
    rsi: float | None = None
    ma5: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    deviation_ma20: float | None = None
    volume_ratio: float | None = None
    change_5d: float | None = None
    change_20d: float | None = None
    volatility_20d: float | None = None


class StockSpotItem(BaseModel):
    code: str
    name: str
    price: float | None
    change_pct: float | None
    pe: float | None = None
    pb: float | None = None
    market_cap: float | None = None
    turnover_rate: float | None = None
    volume_ratio: float | None = None


class StockSpotPage(BaseModel):
    total: int
    page: int
    page_size: int
    stocks: list[StockSpotItem]
