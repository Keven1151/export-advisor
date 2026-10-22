"""WTO Timeseries API client —台灣（Chinese Taipei）官方自行申報的貿易統計。

背景見 CLAUDE.md「台灣代碼」那段：Comtrade 的台灣數字一律是鏡射估計值。台灣雖然不是
聯合國會員（Comtrade拿不到台灣自己的申報資料），但**是WTO正式會員**（會籍名稱
"Chinese Taipei"），WTO規定會員國要自行提交貿易統計給WTO的Integrated Database，
所以這裡查到的是台灣官方真實申報數字，不是推算值，實測跟公開已知的台灣總出口數字
幾乎完全吻合。

**重要限制**：這個API的貿易「金額」類指標（merchandise exports/imports by product
group）只有「全球總額」，沒有拆到個別國家 — 查不到「台灣出口到越南多少」。能拆到
國家的只有「關稅稅率」類指標，不是貿易金額。所以這個資料源只能回答「台灣這個產品類別
的真實總出口值是多少」，回答不了這個工具核心功能需要的「台灣出口到某個特定國家多少」，
那還是得靠 Comtrade（連帶其鏡射估計的限制，見CLAUDE.md）。

品項分類用WTO自己的「SITC3 (aggregates)」約18類，不是HS碼，兩者的對照（概略）見
data/wto_product_groups.py。

免費 key 申請：https://apiportal.wto.org/ 註冊後到 Products > Standard 訂閱
（10 calls/sec，每小時上限10000次，免費）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = "https://api.wto.org/timeseries/v1"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"

CHINESE_TAIPEI_REPORTER_CODE = "158"

_INDICATOR_BY_FLOW = {
    "X": "ITS_MTV_AX",  # Merchandise exports by product group – annual
    "M": "ITS_MTV_AM",  # Merchandise imports by product group – annual
}


class WTOClient:
    def __init__(self, api_key: str | None = None, cache_dir: Path | str = CACHE_DIR):
        self.api_key = api_key or os.environ.get("WTO_API_KEY")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _cache_path(self, flow: str, years: list[int]) -> Path:
        years_label = "-".join(str(y) for y in years)
        return self.cache_dir / f"wto_cht_{flow}_{years_label}.parquet"

    def get_chinese_taipei_trade(
        self, flow: str, years: list[int], use_cache: bool = True
    ) -> pd.DataFrame:
        """查台灣(Chinese Taipei)歷年各品項大類的真實申報出口/進口總額(全球彙總)。

        Args:
            flow: "X" = Export, "M" = Import
            years: 年份清單

        Returns:
            欄位：period, product_code, product_name, trade_value_usd。
            一次會拿回所有品項大類(含"TO"總計)，不是只有單一品項，
            呼叫端自己用 data/wto_product_groups.py 對應到想要的品項再篩選。
            沒設定 WTO_API_KEY 時回傳空表，不拋例外（這個資料源是輔助參考，
            缺key不該讓主要功能掛掉）。
        """
        if not self.is_configured:
            return self._empty_df()

        cache_path = self._cache_path(flow, years)
        if use_cache and cache_path.exists():
            return pd.read_parquet(cache_path)

        raw = self._call_api(flow, years)
        df = self._normalize(raw)

        if use_cache:
            df.to_parquet(cache_path, index=False)
        return df

    def _call_api(self, flow: str, years: list[int]) -> list[dict]:
        indicator = _INDICATOR_BY_FLOW[flow]
        params = {
            "i": indicator,
            "r": CHINESE_TAIPEI_REPORTER_CODE,
            "p": "default",  # 不拆國家，查全球彙總（這個指標本來就沒有國別拆分）
            "ps": ",".join(str(y) for y in years),
            "pc": "default",  # 不指定品項 = 回傳所有品項大類
            "fmt": "json",
            "mode": "full",
            "lang": "1",
            "max": "1000",
        }
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}

        resp = requests.get(f"{BASE_URL}/data", params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("Dataset", [])

    @staticmethod
    def _empty_df() -> pd.DataFrame:
        return pd.DataFrame(columns=["period", "product_code", "product_name", "trade_value_usd"])

    @staticmethod
    def _normalize(raw: list[dict]) -> pd.DataFrame:
        if not raw:
            return WTOClient._empty_df()

        df = pd.DataFrame(raw)
        return pd.DataFrame(
            {
                "period": df["Year"].astype(int),
                "product_code": df["ProductOrSectorCode"],
                "product_name": df["ProductOrSector"],
                # Unit是"Million US dollar"(USM)，轉成美元跟Comtrade/關務署單位一致
                "trade_value_usd": pd.to_numeric(df["Value"], errors="coerce") * 1_000_000,
            }
        )
