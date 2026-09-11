"""UN Comtrade Data API v1 client，含本地 parquet 快取與呼叫頻率節流。

API 文件：https://uncomtrade.org/docs/un-comtrade-api/
- 有 subscription key：呼叫 /data/v1/get/{typeCode}/{freqCode}/{clCode}，資料完整，
  且一次可查多個 period（用逗號分隔）
- 沒有 key：呼叫 /public/v1/preview/{typeCode}/{freqCode}/{clCode}，結果上限 500 筆，
  且**一次只能查一個 period**（多年份會回 400 "Maximum number of periods for preview is 1"），
  可用來先試跑流程，正式使用請申請免費 key（https://comtradeplus.un.org/）

欄位命名、HS 版本規則見專案根目錄 CLAUDE.md。
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from data.country_codes import to_comtrade_code, to_iso3

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = "https://comtradeapi.un.org"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"

# Comtrade classification code -> 人類可讀的 HS 版本標籤（見 CLAUDE.md 欄位命名規則）
CLASSIFICATION_TO_HS_VERSION = {
    "HS": "HS (最新可得版本，混合多年版本，僅供概覽)",
    "H5": "HS2022",
    "H4": "HS2017",
    "H3": "HS2012",
}

# 呼叫間隔節流。官方沒有明確公告免費 key 的速率上限，這裡保守設定：
# - preview（無key）：官方明確限制單次1個period，呼叫次數也偏保守
# - 有 key：可以一次查多年，呼叫次數少很多，間隔可以縮短
MIN_SECONDS_BETWEEN_CALLS_PREVIEW = 6.5
MIN_SECONDS_BETWEEN_CALLS_WITH_KEY = 1.5


class ComtradeClient:
    def __init__(self, api_key: str | None = None, cache_dir: Path | str = CACHE_DIR):
        self.api_key = api_key or os.environ.get("COMTRADE_API_KEY")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_call_ts: float = 0.0

    @property
    def using_preview(self) -> bool:
        return not bool(self.api_key)

    def _throttle(self) -> None:
        min_interval = (
            MIN_SECONDS_BETWEEN_CALLS_PREVIEW
            if self.using_preview
            else MIN_SECONDS_BETWEEN_CALLS_WITH_KEY
        )
        elapsed = time.monotonic() - self._last_call_ts
        wait = min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_call_ts = time.monotonic()

    def _cache_path(
        self,
        reporter_iso: str | None,
        partner_iso: str | None,
        hs_code: str,
        period: str,
        flow: str,
    ) -> Path:
        reporter_label = reporter_iso or "ALL"
        partner_label = partner_iso or "ALL"
        name = f"{reporter_label}_{partner_label}_{hs_code}_{period}_{flow}.parquet"
        return self.cache_dir / name

    def get_trade_data(
        self,
        reporter_iso: str | None,
        partner_iso: str | None,
        hs_code: str,
        period: str,
        flow: str = "M",
        cl_code: str = "HS",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """查詢一組 (reporter, partner, hs_code, period, flow) 的貿易資料。

        Args:
            reporter_iso: 申報國 ISO3，例如 "TWN"（見 country_codes.py 對台灣代碼的說明）；
                傳 None 則查「依所有申報國分列」的明細（用於全球出口/進口國排名）
            partner_iso: 貿易夥伴國 ISO3，例如 "VNM"；查全世界彙總用 "WLD"；
                傳 None 則查「依所有夥伴國分列」的明細（用於競爭國分析）
                注意：reporter_iso 和 partner_iso 不建議同時傳 None，資料量會是完整雙邊貿易矩陣
            hs_code: HS 6 碼字串，例如 "854231"
            period: 年份，例如 "2023"；也可傳多個以逗號分隔，如 "2021,2022,2023"
            flow: "M" = Import（進口）, "X" = Export（出口）
            cl_code: 分類系統，預設 "HS"

        Returns:
            標準化欄位的 DataFrame（見 CLAUDE.md 資料欄位命名），查無資料時回傳空 DataFrame。
        """
        periods = [p.strip() for p in str(period).split(",") if p.strip()]

        if self.using_preview:
            # preview 端點一次只接受1個period，逐年查詢+逐年快取
            frames = [
                self._get_cached_or_call(reporter_iso, partner_iso, hs_code, p, flow, cl_code, use_cache)
                for p in periods
            ]
        else:
            # 有 key 的完整端點支援一次查多年；優先看快取是否已經有「全部年份合併」的
            # 那一筆，沒有的話才發一次多年 API call（比逐年 call 快很多）
            joined_period = ",".join(periods)
            frames = [
                self._get_cached_or_call(
                    reporter_iso, partner_iso, hs_code, joined_period, flow, cl_code, use_cache
                )
            ]

        frames = [f for f in frames if not f.empty]
        if not frames:
            return self._normalize([])
        return pd.concat(frames, ignore_index=True)

    def _get_cached_or_call(
        self,
        reporter_iso: str | None,
        partner_iso: str | None,
        hs_code: str,
        period: str,
        flow: str,
        cl_code: str,
        use_cache: bool,
    ) -> pd.DataFrame:
        cache_path = self._cache_path(reporter_iso, partner_iso, hs_code, period, flow)
        if use_cache and cache_path.exists():
            logger.info("cache hit: %s", cache_path.name)
            return pd.read_parquet(cache_path)

        raw = self._call_api(reporter_iso, partner_iso, hs_code, period, flow, cl_code)
        df = self._normalize(raw)

        if use_cache:
            df.to_parquet(cache_path, index=False)
        return df

    def _call_api(
        self,
        reporter_iso: str | None,
        partner_iso: str | None,
        hs_code: str,
        period: str,
        flow: str,
        cl_code: str,
    ) -> list[dict]:
        params = {
            "period": period,
            "cmdCode": hs_code,
            "flowCode": flow,
            "motCode": "0",
            "partner2Code": "0",
            "customsCode": "C00",
            "includeDesc": "true",
        }
        if reporter_iso is not None:
            # 不帶 reporterCode = 依所有申報國分列明細，用於全球出口/進口國排名
            params["reporterCode"] = to_comtrade_code(reporter_iso)
        if partner_iso is not None:
            # 不帶 partnerCode = 依所有夥伴國分列明細，用於競爭國分析
            params["partnerCode"] = to_comtrade_code(partner_iso)

        headers = {}
        if self.api_key:
            url = f"{BASE_URL}/data/v1/get/C/A/{cl_code}"
            headers["Ocp-Apim-Subscription-Key"] = self.api_key
        else:
            url = f"{BASE_URL}/public/v1/preview/C/A/{cl_code}"
            logger.warning(
                "沒有設定 COMTRADE_API_KEY，改用 preview 端點（結果上限500筆，僅供試跑）"
            )

        # 429限制是短時間爆量觸發（實測：連續呼叫約15-16次後開始429，官方訊息通常是
        # "Try again in 1 seconds"），不是穩定的每分鐘上限，所以遇到429用退避重試，
        # 而不是直接整個查詢失敗
        max_retries = 4
        backoff_seconds = 2.0
        for attempt in range(max_retries + 1):
            self._throttle()
            resp = requests.get(url, params=params, headers=headers, timeout=60)
            if resp.status_code != 429:
                break
            if attempt == max_retries:
                raise RuntimeError(
                    "Comtrade API 回傳 429 Too Many Requests，重試多次仍失敗，請稍後再試"
                )
            logger.warning(
                "Comtrade API 429 Too Many Requests，%s秒後重試（第%d次）",
                backoff_seconds,
                attempt + 1,
            )
            time.sleep(backoff_seconds)
            backoff_seconds *= 2

        resp.raise_for_status()

        payload = resp.json()
        return payload.get("data", [])

    @staticmethod
    def _normalize(raw: list[dict]) -> pd.DataFrame:
        if not raw:
            return pd.DataFrame(
                columns=[
                    "period",
                    "reporter_iso",
                    "partner_iso",
                    "hs_code",
                    "hs_version",
                    "trade_flow",
                    "trade_value_usd",
                    "net_weight_kg",
                    "is_reported",
                ]
            )

        df = pd.DataFrame(raw)
        out = pd.DataFrame(
            {
                # API 回傳 period 是字串（如"2023"），下游會拿來做算術/排序，一律轉int
                "period": pd.to_numeric(df.get("period"), errors="coerce").astype("Int64"),
                "reporter_iso": df.get("reporterCode").apply(to_iso3)
                if "reporterCode" in df
                else None,
                "partner_iso": df.get("partnerCode").apply(to_iso3)
                if "partnerCode" in df
                else None,
                "hs_code": df.get("cmdCode").astype(str),
                "hs_version": df.get("classificationCode", "HS"),
                "trade_flow": df.get("flowDesc", df.get("flowCode")),
                "trade_value_usd": pd.to_numeric(df.get("primaryValue"), errors="coerce"),
                "net_weight_kg": pd.to_numeric(df.get("netWgt"), errors="coerce"),
                # 是否為該國「自行申報」的數字；台灣(reporterCode=490)一律是False，
                # 全部是用夥伴國鏡射資料推算的估計值，見 CLAUDE.md 台灣代碼那段說明
                "is_reported": df.get("isReported") if "isReported" in df else None,
            }
        )
        return out
