"""F1：目標國進出口趨勢分析（見 PRD.md §5 F1）。

輸入台灣（或指定申報國）某 HS code 對目標國的歷年出口資料，計算量值趨勢、YoY、CAGR，
並算出台灣在該國該 HS code 進口總額中的市占率變化（需要另外查「目標國從全世界進口」
的資料作分母，見 `market_share`）。
"""

from __future__ import annotations

import pandas as pd

from data.comtrade_client import ComtradeClient


def export_trend(
    client: ComtradeClient,
    hs_code: str,
    target_country_iso: str,
    reporter_iso: str = "TWN",
    years: list[int] | None = None,
) -> pd.DataFrame:
    """回傳 reporter -> target_country 的歷年出口趨勢，含 YoY 成長率。

    Returns:
        欄位：period, trade_value_usd, net_weight_kg, yoy_growth
    """
    years = years or default_years()
    period = ",".join(str(y) for y in years)

    df = client.get_trade_data(
        reporter_iso=reporter_iso,
        partner_iso=target_country_iso,
        hs_code=hs_code,
        period=period,
        flow="X",
    )
    if df.empty:
        return df.assign(yoy_growth=pd.Series(dtype=float))

    df = df.sort_values("period").reset_index(drop=True)
    df["yoy_growth"] = df["trade_value_usd"].pct_change()
    return df


def cagr(df: pd.DataFrame, value_col: str = "trade_value_usd") -> float | None:
    """算 CAGR。資料點不足 2 個或起始值為 0/負值則回傳 None（避免除以0或算出無意義負成長率）。"""
    if len(df) < 2:
        return None
    df = df.sort_values("period")
    start_val = df[value_col].iloc[0]
    end_val = df[value_col].iloc[-1]
    n_years = df["period"].iloc[-1] - df["period"].iloc[0]
    if start_val <= 0 or n_years <= 0:
        return None
    return (end_val / start_val) ** (1 / n_years) - 1


def market_share(
    client: ComtradeClient,
    hs_code: str,
    target_country_iso: str,
    reporter_iso: str = "TWN",
    years: list[int] | None = None,
) -> pd.DataFrame:
    """台灣出口占目標國「從全世界進口該HS code」總額的市占率，逐年計算。

    Returns:
        欄位：period, reporter_export_usd, world_import_usd, market_share_pct
    """
    years = years or default_years()
    period = ",".join(str(y) for y in years)

    reporter_df = client.get_trade_data(
        reporter_iso=reporter_iso,
        partner_iso=target_country_iso,
        hs_code=hs_code,
        period=period,
        flow="X",
    )
    world_df = client.get_trade_data(
        reporter_iso=target_country_iso,
        partner_iso="WLD",
        hs_code=hs_code,
        period=period,
        flow="M",
    )

    reporter_agg = reporter_df.groupby("period")["trade_value_usd"].sum().rename("reporter_export_usd")
    world_agg = world_df.groupby("period")["trade_value_usd"].sum().rename("world_import_usd")

    merged = pd.concat([reporter_agg, world_agg], axis=1).reset_index()
    merged["market_share_pct"] = (
        merged["reporter_export_usd"] / merged["world_import_usd"] * 100
    ).where(merged["world_import_usd"] > 0)
    return merged.sort_values("period")


def default_years(n: int = 5) -> list[int]:
    import datetime

    current_year = datetime.date.today().year
    # Comtrade 通常有1-2年落後，預設抓到去年即可，避免查到還沒有資料的年份
    latest = current_year - 1
    return list(range(latest - n + 1, latest + 1))
