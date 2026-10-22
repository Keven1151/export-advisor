"""全球視角的產品貿易分析：這個HS code全世界誰在出口、誰在進口，以及主要出口國的
優劣勢比較（見使用者需求：「該產品出口國趨勢」「主要競爭國/出口國優劣勢分析」）。

跟 competitor_analysis.py 的差異：competitor_analysis 是「給定一個目標國，看誰在
賣給它」；這個模組是「不限定目標國，看全世界誰在賣/誰在買這個產品」。
"""

from __future__ import annotations

import pandas as pd

from data.comtrade_client import ComtradeClient
from analysis.trend_analysis import cagr, default_years


def _full_country_series(
    client: ComtradeClient, hs_code: str, years: list[int], flow: str
) -> pd.DataFrame:
    """依申報國(reporter)彙整對全世界的貿易額，回傳**所有**有資料的國家、完整歷年序列
    （不截斷排名），world_share_pct / rank 都是相對「全部申報國」計算的。

    截斷成「前N大」的邏輯交給呼叫端做（見 `_country_ranking`），因為像
    `exporter_scorecard` 需要查詢「使用者指定的國家」，那個國家不一定排得進前N大
    （台灣常常就是這種情況——見 CLAUDE.md 台灣資料估計值的說明），如果在這裡就先
    截斷，之後就永遠查不到那個國家的資料了。

    Returns:
        欄位：period, reporter_iso, trade_value_usd, net_weight_kg, world_share_pct, rank
    """
    period = ",".join(str(y) for y in years)
    df = client.get_trade_data(
        reporter_iso=None, partner_iso="WLD", hs_code=hs_code, period=period, flow=flow
    )
    if df.empty:
        return df

    df = df.dropna(subset=["reporter_iso"])
    agg = df.groupby(["period", "reporter_iso"], as_index=False)[
        ["trade_value_usd", "net_weight_kg"]
    ].sum()

    year_totals = agg.groupby("period")["trade_value_usd"].transform("sum")
    agg["world_share_pct"] = agg["trade_value_usd"] / year_totals * 100
    agg["rank"] = agg.groupby("period")["trade_value_usd"].rank(ascending=False, method="min")
    return agg.sort_values(["period", "rank"]).reset_index(drop=True)


def _country_ranking(
    client: ComtradeClient,
    hs_code: str,
    years: list[int],
    flow: str,
    top_n: int,
    always_include: str | None = None,
) -> pd.DataFrame:
    """`_full_country_series` 的結果，取「最新年度」前N大，並保留這些國家完整的歷年序列
    （即使某國在較早年度不在前N大，只要現在是前N大就會有完整趨勢線）。只給圖表用，
    需要查特定國家（不管排名）請直接用 `_full_country_series`。

    Args:
        always_include: 不管排名多少都要強制納入結果的國家（例如台灣）。這個工具主要是
            給台灣企業用的，但台灣在 Comtrade 常常擠不進全球前N大（見CLAUDE.md台灣資料
            估計值的說明），如果不強制納入，使用者會完全看不到自己國家的資料，誤以為
            「台灣沒有這個產品的出口資料」。只在該國真的有查到任何資料時才會加入，
            完全查無資料（含鏡射估計）不會硬塞一個空的進去。
    """
    full = _full_country_series(client, hs_code, years, flow)
    if full.empty:
        return full

    latest_period = full["period"].max()
    top_countries = (
        full[full["period"] == latest_period].sort_values("rank").head(top_n)["reporter_iso"].tolist()
    )
    if always_include and always_include not in top_countries:
        if always_include in full["reporter_iso"].unique():
            top_countries.append(always_include)

    result = full[full["reporter_iso"].isin(top_countries)].sort_values(["period", "rank"])
    return result.reset_index(drop=True)


def world_exporter_ranking(
    client: ComtradeClient,
    hs_code: str,
    years: list[int] | None = None,
    top_n: int = 15,
    always_include: str | None = None,
) -> pd.DataFrame:
    """這個HS code全球最大的出口國排名（目前主要玩家是誰），回傳前N大 + always_include
    指定的國家（通常是使用者自己的出口國，即使排不進前N大也要讓它看得到自己的資料）。
    """
    years = years or default_years()
    return _country_ranking(client, hs_code, years, flow="X", top_n=top_n, always_include=always_include)


def world_importer_ranking(
    client: ComtradeClient,
    hs_code: str,
    years: list[int] | None = None,
    top_n: int = 15,
    always_include: str | None = None,
) -> pd.DataFrame:
    """這個HS code全球最大的進口市場排名（潛在目標國候選清單的來源），回傳前N大 +
    always_include 指定的國家。
    """
    years = years or default_years()
    return _country_ranking(client, hs_code, years, flow="M", top_n=top_n, always_include=always_include)


def exporter_scorecard(
    client: ComtradeClient,
    hs_code: str,
    exporter_isos: list[str],
    years: list[int] | None = None,
) -> pd.DataFrame:
    """主要出口國優劣勢比較表。

    對每個出口國計算：
    - world_share_pct：最新年度全球出口市占（越高＝規模優勢）
    - export_cagr：出口值成長率（越高＝動能優勢）
    - avg_unit_price_usd_per_kg：最新年度平均單價（僅供價格定位參考，
      未依產品細目/品質分級，不能直接當作「貴=劣勢/便宜=優勢」，可能反映高階/低階市場定位）
    - destination_hhi：該國出口目的地集中度（越高＝客戶集中、地緣風險越高；
      越低＝市場分散，較不怕單一市場需求波動）
    - destination_count：該國有實際出口記錄的目的地數（市場滲透廣度）

    Returns:
        欄位：reporter_iso, world_share_pct, export_cagr, avg_unit_price_usd_per_kg,
        destination_hhi, destination_count，依 world_share_pct 由高到低排序。
        若某國完全查無出口資料（沒有任何申報/鏡射紀錄），該國不會出現在結果裡。
    """
    years = years or default_years()
    # 用未截斷的完整序列查，不能用 world_exporter_ranking（只回傳前N大），
    # 否則像台灣這種常常排不進全球前N大的國家會直接被漏掉，見上面 `_full_country_series` 的說明
    full_series = _full_country_series(client, hs_code, years, flow="X")
    if full_series.empty:
        return pd.DataFrame()

    latest_year = full_series["period"].max()
    rows = []

    for iso in exporter_isos:
        country_series = full_series[full_series["reporter_iso"] == iso].sort_values("period")
        if country_series.empty:
            continue

        latest_row = country_series[country_series["period"] == latest_year]
        world_share = latest_row["world_share_pct"].iloc[0] if not latest_row.empty else None
        growth = cagr(country_series)

        unit_price = None
        if not latest_row.empty:
            wgt = latest_row["net_weight_kg"].iloc[0]
            val = latest_row["trade_value_usd"].iloc[0]
            if wgt and wgt > 0:
                unit_price = val / wgt

        dest_df = client.get_trade_data(
            reporter_iso=iso, partner_iso=None, hs_code=hs_code, period=str(latest_year), flow="X"
        )
        hhi = None
        dest_count = None
        if not dest_df.empty:
            dest_agg = dest_df.dropna(subset=["partner_iso"]).groupby("partner_iso")[
                "trade_value_usd"
            ].sum()
            dest_agg = dest_agg[dest_agg > 0]
            dest_count = int(dest_agg.shape[0])
            total = dest_agg.sum()
            if total > 0:
                shares = dest_agg / total * 100
                hhi = float((shares**2).sum())

        rows.append(
            {
                "reporter_iso": iso,
                "world_share_pct": world_share,
                "export_cagr": growth,
                "avg_unit_price_usd_per_kg": unit_price,
                "destination_hhi": hhi,
                "destination_count": dest_count,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values("world_share_pct", ascending=False, na_position="last").reset_index(
        drop=True
    )
