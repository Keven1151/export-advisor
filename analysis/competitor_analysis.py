"""F2：競爭國分析（見 PRD.md §5 F2）。

給定目標國 + HS code，找出：
1. 該國過去N年所有進口來源國排名與市占變化
2. 台灣與前5大競爭國的平均單價比較
3. 跨多個 (目標國, HS code) 組合，篩出「進口成長快、但台灣市占仍低」的機會缺口
"""

from __future__ import annotations

import pandas as pd

from data.comtrade_client import ComtradeClient
from analysis.trend_analysis import cagr, market_share, default_years


def competitor_ranking(
    client: ComtradeClient,
    hs_code: str,
    target_country_iso: str,
    years: list[int] | None = None,
    top_n: int = 10,
) -> pd.DataFrame:
    """目標國該HS code的進口來源國排名，逐年計算市占率與名次變化。

    Returns:
        欄位：period, partner_iso, trade_value_usd, rank, market_share_pct
    """
    years = years or default_years()
    period = ",".join(str(y) for y in years)

    df = client.get_trade_data(
        reporter_iso=target_country_iso,
        partner_iso=None,  # 依所有夥伴國分列
        hs_code=hs_code,
        period=period,
        flow="M",
    )
    if df.empty:
        return df

    df = df.dropna(subset=["partner_iso"])
    agg = df.groupby(["period", "partner_iso"], as_index=False)["trade_value_usd"].sum()

    agg["rank"] = agg.groupby("period")["trade_value_usd"].rank(ascending=False, method="min")
    year_totals = agg.groupby("period")["trade_value_usd"].transform("sum")
    agg["market_share_pct"] = agg["trade_value_usd"] / year_totals * 100

    agg = agg.sort_values(["period", "rank"])
    return agg.groupby("period", group_keys=False).head(top_n).reset_index(drop=True)


def price_comparison(
    ranking_df: pd.DataFrame,
    raw_trade_df: pd.DataFrame,
    reporter_iso: str = "TWN",
    top_n_competitors: int = 5,
) -> pd.DataFrame:
    """台灣 vs 前 N 大競爭國的平均單價（trade_value_usd / net_weight_kg）比較。

    Args:
        ranking_df: competitor_ranking() 的輸出，用來決定最新一年的前N大競爭國名單
        raw_trade_df: get_trade_data(target_country, partner_iso=None, ...) 的原始明細，
            要含 net_weight_kg 才能算單價

    Returns:
        欄位：period, partner_iso, unit_price_usd_per_kg，只含台灣+前N大競爭國
    """
    if ranking_df.empty or raw_trade_df.empty:
        return pd.DataFrame(columns=["period", "partner_iso", "unit_price_usd_per_kg"])

    latest_period = ranking_df["period"].max()
    top_competitors = (
        ranking_df[ranking_df["period"] == latest_period]
        .sort_values("rank")
        .head(top_n_competitors)["partner_iso"]
        .tolist()
    )
    countries_of_interest = list(set(top_competitors) | {reporter_iso})

    df = raw_trade_df[raw_trade_df["partner_iso"].isin(countries_of_interest)].copy()
    agg = df.groupby(["period", "partner_iso"], as_index=False)[
        ["trade_value_usd", "net_weight_kg"]
    ].sum()
    agg["unit_price_usd_per_kg"] = (agg["trade_value_usd"] / agg["net_weight_kg"]).where(
        agg["net_weight_kg"] > 0
    )
    return agg[["period", "partner_iso", "unit_price_usd_per_kg"]].sort_values(
        ["period", "partner_iso"]
    )


def growth_opportunity_gaps(
    client: ComtradeClient,
    hs_codes: list[str],
    target_countries_iso: list[str],
    reporter_iso: str = "TWN",
    years: list[int] | None = None,
    min_cagr: float = 0.05,
    max_market_share_pct: float = 5.0,
) -> pd.DataFrame:
    """掃描多個 (HS code, 目標國) 組合，找出「進口成長快、台灣市占仍低」的機會缺口。

    Args:
        min_cagr: 目標國該HS code的進口 CAGR 門檻，預設 5%
        max_market_share_pct: 台灣市占率上限（低於此值才算「仍低」），預設 5%

    Returns:
        欄位：hs_code, target_country_iso, import_cagr, latest_taiwan_share_pct，
        依 import_cagr 由高到低排序
    """
    years = years or default_years()
    rows = []

    for hs_code in hs_codes:
        for country in target_countries_iso:
            share_df = market_share(
                client, hs_code, country, reporter_iso=reporter_iso, years=years
            )
            if share_df.empty or share_df["world_import_usd"].notna().sum() < 2:
                continue

            import_growth = cagr(
                share_df.rename(columns={"world_import_usd": "trade_value_usd"})
            )
            latest_share = share_df.sort_values("period")["market_share_pct"].iloc[-1]

            if import_growth is None:
                continue
            if import_growth >= min_cagr and (
                pd.isna(latest_share) or latest_share <= max_market_share_pct
            ):
                rows.append(
                    {
                        "hs_code": hs_code,
                        "target_country_iso": country,
                        "import_cagr": import_growth,
                        "latest_taiwan_share_pct": latest_share,
                    }
                )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values("import_cagr", ascending=False).reset_index(drop=True)
