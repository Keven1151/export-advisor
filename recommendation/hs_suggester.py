"""F3：HS Code 拓銷建議（見 PRD.md §5 F3）。

流程：
1. 用文字相似度，從 Comtrade 官方 HS 6碼清單中找出跟產品描述最接近的候選碼
2. 對每個候選碼查目標國的進口成長率 (CAGR)、市場集中度 (HHI)、台灣目前市占
3. 綜合評分排序

**重要**：輸出的 HS code 僅為初步篩選建議，正式報關／產證申請前必須洽專業報關業者
確認 6 碼以下細目（見 CLAUDE.md「HS Code 規則」）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import requests
from rapidfuzz import process, fuzz

from data.comtrade_client import ComtradeClient
from analysis.trend_analysis import cagr, default_years, market_share
from analysis.competitor_analysis import competitor_ranking

logger = logging.getLogger(__name__)

HS_REFERENCE_URL = "https://comtradeapi.un.org/files/v1/app/reference/HS.json"
HS_REFERENCE_CACHE = Path(__file__).resolve().parent.parent / "cache" / "hs_reference.json"

DISCLAIMER = (
    "本清單為初步篩選建議，僅供拓銷方向參考；正式報關、產證申請或關稅稅則確認，"
    "請務必洽專業報關業者複核 HS 6 碼以下細目。"
)


def load_hs_reference(force_refresh: bool = False) -> pd.DataFrame:
    """載入 Comtrade 官方 HS 6碼清單（含英文品名），本地快取避免每次都下載。

    Returns:
        欄位：hs_code, description
    """
    if not force_refresh and HS_REFERENCE_CACHE.exists():
        raw = json.loads(HS_REFERENCE_CACHE.read_text(encoding="utf-8"))
    else:
        resp = requests.get(HS_REFERENCE_URL, timeout=30)
        resp.raise_for_status()
        raw = resp.json()
        HS_REFERENCE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        HS_REFERENCE_CACHE.write_text(json.dumps(raw), encoding="utf-8")

    results = raw.get("results", [])
    rows = [
        {"hs_code": r["id"], "description": r["text"]}
        for r in results
        if r.get("isLeaf") == "1" and len(r.get("id", "")) == 6 and r["id"].isdigit()
    ]
    return pd.DataFrame(rows)


def find_candidate_hs_codes(
    product_description: str, hs_reference: pd.DataFrame, top_n: int = 10
) -> pd.DataFrame:
    """用文字相似度找出跟產品描述最接近的候選 HS 6碼（英文描述比對，中文描述效果有限，
    建議使用者同時輸入英文關鍵字以提高命中率）。

    Returns:
        欄位：hs_code, description, similarity_score (0-100)
    """
    choices = hs_reference["description"].tolist()
    matches = process.extract(
        product_description, choices, scorer=fuzz.token_set_ratio, limit=top_n
    )

    rows = []
    for description, score, idx in matches:
        row = hs_reference.iloc[idx]
        rows.append(
            {"hs_code": row["hs_code"], "description": row["description"], "similarity_score": score}
        )
    return pd.DataFrame(rows)


def _hhi(market_share_pcts: pd.Series) -> float | None:
    """Herfindahl-Hirschman Index，用市占率百分比算，範圍 0-10000。越高代表市場越集中
    （被少數國家壟斷），越低代表越分散、新進入者相對有機會。"""
    shares = market_share_pcts.dropna()
    if shares.empty:
        return None
    return float((shares**2).sum())


def score_candidates(
    client: ComtradeClient,
    candidates: pd.DataFrame,
    target_country_iso: str,
    reporter_iso: str = "TWN",
    years: list[int] | None = None,
) -> pd.DataFrame:
    """對每個候選HS code查目標國進口成長率、市場集中度、台灣現有市占，並算綜合分數。

    評分邏輯（0-100，越高越值得優先評估）：
    - 成長率佔 50 分：CAGR 以 20% 封頂，等比例給分
    - 市場分散度佔 30 分：HHI 越低分數越高（HHI<=1500 給滿分，>=5000 給0分，中間內插）
    - 文字相似度佔 20 分：similarity_score 等比例給分

    Returns:
        欄位：hs_code, description, similarity_score, import_cagr, hhi,
        latest_taiwan_share_pct, opportunity_score
    """
    years = years or default_years()
    rows = []

    for _, cand in candidates.iterrows():
        hs_code = cand["hs_code"]
        try:
            share_df = market_share(
                client, hs_code, target_country_iso, reporter_iso=reporter_iso, years=years
            )
            ranking_df = competitor_ranking(
                client, hs_code, target_country_iso, years=years, top_n=250
            )
        except Exception:
            logger.exception("查詢 HS code %s 失敗，略過", hs_code)
            continue

        import_growth = None
        latest_share = None
        if not share_df.empty and share_df["world_import_usd"].notna().sum() >= 2:
            import_growth = cagr(share_df.rename(columns={"world_import_usd": "trade_value_usd"}))
            latest_share = share_df.sort_values("period")["market_share_pct"].iloc[-1]

        hhi = None
        if not ranking_df.empty:
            latest_period = ranking_df["period"].max()
            hhi = _hhi(ranking_df[ranking_df["period"] == latest_period]["market_share_pct"])

        rows.append(
            {
                "hs_code": hs_code,
                "description": cand["description"],
                "similarity_score": cand["similarity_score"],
                "import_cagr": import_growth,
                "hhi": hhi,
                "latest_taiwan_share_pct": latest_share,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    growth_score = (result["import_cagr"].clip(lower=0, upper=0.20) / 0.20 * 50).fillna(0)

    hhi_clipped = result["hhi"].clip(lower=1500, upper=5000)
    dispersion_score = ((5000 - hhi_clipped) / (5000 - 1500) * 30).fillna(15)  # 缺資料給中間值

    similarity_score = result["similarity_score"] / 100 * 20

    result["opportunity_score"] = (growth_score + dispersion_score + similarity_score).round(1)
    return result.sort_values("opportunity_score", ascending=False).reset_index(drop=True)


def suggest_hs_codes(
    client: ComtradeClient,
    product_description: str,
    target_country_iso: str,
    reporter_iso: str = "TWN",
    years: list[int] | None = None,
    n_candidates: int = 10,
) -> tuple[pd.DataFrame, str]:
    """完整流程：文字比對候選碼 -> 查貿易資料 -> 評分排序。

    Returns:
        (評分結果 DataFrame, 免責提示文字)
    """
    reference = load_hs_reference()
    candidates = find_candidate_hs_codes(product_description, reference, top_n=n_candidates)
    scored = score_candidates(
        client, candidates, target_country_iso, reporter_iso=reporter_iso, years=years
    )
    return scored, DISCLAIMER
