from msgspec import Struct


# - - Binance Futures USDM
class AggTrade(Struct):
    T: int  # Trade time
    p: float  # Price
    q: float  # Quantity
    m: bool  # Is buyer maker?


class AggTradeSim(Struct):
    e: str  # Event name
    E: int  # Event time
    a: int  # Agg Trade id
    s: str  # Symbol
    p: str  # Price
    q: str  # Quantity
    f: int  # First trade id
    l: int  # Last trade id # noqa
    T: int  # Trade time
    m: bool  # Is buyer maker
