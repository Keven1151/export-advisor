"""建議此產品出口具有優勢的目標國家（見使用者新增需求 #4）。

流程：
1. 從全球進口排名找出這個HS code最大的N個進口市場，當作候選目標國
2. 對每個候選市場，計算：市場規模、進口成長率、exporter現有市占、
   供應商集中度(HHI，越低越容易切入)、exporter相對前5大競爭者的單價優劣
3. 綜合評分排序

**重要**：評分僅根據公開貿易統計計算，不含關稅、法規、通路、實地市場資訊，
僅供拓銷優先順序的初步參考。
"""

from __future__ import annotations

import pandas as pd

from data.comtrade_client import ComtradeClient
from analysis.trend_analysis import cagr, market_share, default_years
from analysis.competitor_analysis import competitor_ranking, price_comparison
from analysis.global_trade import world_importer_ranking

DISCLAIMER = (
    "本清單為根據公開貿易統計計算的初步分析，僅供評估目標市場優先順序參考，"
    "實際拓銷決策請一併考慮關稅稅率、法規標準、通路關係與實地市場調查。"
)


def recommend_target_markets(
    client: ComtradeClient,
    hs_code: str,
    exporter_iso: str = "TWN",
    years: list[int] | None = None,
    n_candidates: int = 10,
) -> tuple[pd.DataFrame, str]:
    """建議 exporter_iso（預設台灣）出口這個HS code具有優勢的目標國家清單。

    Returns:
        (評分結果 DataFrame, 免責提示文字)。DataFrame 欄位：
        target_country_iso, market_size_usd, import_cagr, exporter_share_pct,
        supplier_hhi, price_advantage_pct, target_score（0-100，越高越值得優先評估）
    """
    years = years or default_years()
    importer_ranking = world_importer_ranking(client, hs_code, years, top_n=n_candidates)
    if importer_ranking.empty:
        return importer_ranking, DISCLAIMER

    latest_year = importer_ranking["period"].max()
    candidate_countries = [
        c
        for c in importer_ranking[importer_ranking["period"] == latest_year]["reporter_iso"].tolist()
        if c != exporter_iso
    ]

    rows = []
    for country in candidate_countries:
        market_series = importer_ranking[importer_ranking["reporter_iso"] == country].sort_values(
            "period"
        )
        import_growth = cagr(market_series)
        latest_market_row = market_series[market_series["period"] == latest_year]
        market_size_usd = (
            latest_market_row["trade_value_usd"].iloc[0] if not latest_market_row.empty else None
        )

        share_df = market_share(client, hs_code, country, reporter_iso=exporter_iso, years=years)
        exporter_share = None
        if not share_df.empty:
            latest_share_row = share_df[share_df["period"] == latest_year]
            if not latest_share_row.empty:
                exporter_share = latest_share_row["market_share_pct"].iloc[0]

        ranking_df = competitor_ranking(client, hs_code, country, years=[latest_year], top_n=250)
        hhi = None
        price_gap_pct = None
        if not ranking_df.empty:
            hhi = float((ranking_df["market_share_pct"] ** 2).sum())

            raw_df = client.get_trade_data(
                reporter_iso=country,
                partner_iso=None,
                hs_code=hs_code,
                period=str(latest_year),
                flow="M",
            )
            price_df = price_comparison(ranking_df, raw_df, reporter_iso=exporter_iso, top_n_competitors=5)
            if not price_df.empty:
                exporter_price = price_df.loc[
                    price_df["partner_iso"] == exporter_iso, "unit_price_usd_per_kg"
                ]
                competitor_prices = price_df.loc[
                    price_df["partner_iso"] != exporter_iso, "unit_price_usd_per_kg"
                ].dropna()
                if not exporter_price.empty and pd.notna(exporter_price.iloc[0]) and not competitor_prices.empty:
                    median_competitor_price = competitor_prices.median()
                    if median_competitor_price:
                        price_gap_pct = (
                            (median_competitor_price - exporter_price.iloc[0])
                            / median_competitor_price
                            * 100
                        )

        rows.append(
            {
                "target_country_iso": country,
                "market_size_usd": market_size_usd,
                "import_cagr": import_growth,
                "exporter_share_pct": exporter_share,
                "supplier_hhi": hhi,
                "price_advantage_pct": price_gap_pct,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result, DISCLAIMER

    # 評分邏輯（0-100，越高越值得優先評估）：
    # - 市場成長率 35分：CAGR 以 20% 封頂等比例給分
    # - 市場規模 20分：候選國之間相對排名 (百分位)
    # - exporter現有市占 20分：0-20% 封頂等比例給分（有基礎、風險較低）
    # - 供應商分散度 15分：HHI 越低分越高（越容易切入）
    # - 價格優勢 10分：exporter單價比前5大競爭者中位數便宜/貴的百分比，±20%封頂
    growth_score = (result["import_cagr"].clip(lower=0, upper=0.20) / 0.20 * 35).fillna(0)
    size_score = result["market_size_usd"].rank(pct=True).fillna(0.5) * 20
    share_score = (result["exporter_share_pct"].clip(lower=0, upper=20) / 20 * 20).fillna(0)
    hhi_clipped = result["supplier_hhi"].clip(lower=1000, upper=5000)
    accessibility_score = ((5000 - hhi_clipped) / (5000 - 1000) * 15).fillna(7.5)
    price_score = (result["price_advantage_pct"].clip(lower=-20, upper=20) / 20 * 10).fillna(0)

    result["target_score"] = (
        growth_score + size_score + share_score + accessibility_score + price_score
    ).round(1)

    return result.sort_values("target_score", ascending=False).reset_index(drop=True), DISCLAIMER
