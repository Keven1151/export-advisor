"""財政部關務署官方貿易統計 client（用來粗略交叉比對 Comtrade 對台灣資料的估計值）。

背景見 CLAUDE.md「台灣代碼」那段：Comtrade 的台灣數字(reporterCode=490)一律是用
夥伴國鏡射資料推算的估計值，不是自行申報。財政部關務署才是台灣海關的官方自行申報數字，
但公開資料集只到 **HS Section(19類，比HS2碼章別更粗，見 data/hs_sections.py)**、
且只有 **5個特定夥伴國/地區分組**（中國大陸與香港、日本、韓國、美國、東協），
沒有HS 6碼×任意國家的組合，所以只能拿來做「量級/方向對不對」的粗略交叉比對，
不能拿來取代 Comtrade 的精確數字。

資料來源：data.gov.tw 資料集 28573（財政部關務署「按HS及主要國別(地區)分」進出口統計），
底層是財政部「財政統計資料庫」的CSV匯出網址，沒有正式API文件，網址結構可能因網站改版而失效。
"""

from __future__ import annotations

import logging
import re
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

CSV_URL = (
    "https://web02.mof.gov.tw/njswww/webMain.aspx?sys=220&ym=9000&kind=21&type=4"
    "&funid=i9901&cycle=41&outmode=12&compmode=00&outkind=1"
    "&fldspc=0,1,3,4,&codlst0=11&codspc1=0,20,&utf=1"
)
CACHE_PATH = Path(__file__).resolve().parent.parent / "cache" / "mof_customs_by_section.parquet"

# 資料集裡的夥伴分組 <-> 本專案 ISO3 的對應。東協是多國合併，無法對應到單一ISO3，
# 只列出成員國清單供參考用途（例如提示使用者「越南的官方參考數字包含在東協分組裡，無法單獨拆出」）
PARTNER_GROUP_TO_ISO3 = {
    "中國大陸與香港": ["CHN", "HKG"],
    "日本": ["JPN"],
    "韓國": ["KOR"],
    "美國": ["USA"],
    "東協": ["BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "VNM"],
}

_FLOW_ZH_TO_EN = {"進口": "Import", "出口": "Export"}

_ANNUAL_PERIOD_RE = re.compile(r"^(\d+)年$")
_COLUMN_RE = re.compile(r"^(.+?)/\s*(進口|出口)/\s*(.+?)\(千美元\)$")


def iso3_to_partner_group(iso3: str) -> str | None:
    """ISO3轉關務署的夥伴分組名稱，查不到（不在5個分組裡）回傳None。"""
    iso3 = iso3.upper().strip()
    for group, members in PARTNER_GROUP_TO_ISO3.items():
        if iso3 in members:
            return group
    return None


def _fetch_raw_csv() -> str:
    resp = requests.get(CSV_URL, timeout=60)
    resp.raise_for_status()
    return resp.content.decode("utf-8-sig")


def _parse_csv(raw_csv: str) -> pd.DataFrame:
    """把原始寬表CSV(1個period欄+200個「分組/流向/類別」欄)轉成長表。

    Returns:
        欄位：period(int,西元年), partner_group, flow(Export/Import),
        section_no(int,0代表該分組總計), section_desc, trade_value_usd(float)
    """
    wide = pd.read_csv(StringIO(raw_csv))
    period_col = wide.columns[0]  # header寫「國家別」但實際存的是期別，官方CSV本身標錯欄名

    wide = wide[wide[period_col].astype(str).str.match(_ANNUAL_PERIOD_RE)].copy()
    wide["period"] = (
        wide[period_col].astype(str).str.extract(_ANNUAL_PERIOD_RE)[0].astype(int) + 1911
    )

    rows = []
    for col in wide.columns:
        if col in (period_col, "period"):
            continue
        match = _COLUMN_RE.match(col.strip())
        if not match:
            continue
        partner_group, flow_zh, section_label = match.groups()
        section_label = section_label.strip()

        if section_label == "總計":
            section_no, section_desc = 0, "總計"
        else:
            no_str, _, desc = section_label.partition(".")
            if not no_str.isdigit():
                continue
            section_no, section_desc = int(no_str), desc

        values = pd.to_numeric(wide[col], errors="coerce") * 1000  # 千美元 -> 美元，跟Comtrade單位一致
        for period, value in zip(wide["period"], values):
            rows.append(
                {
                    "period": int(period),
                    "partner_group": partner_group,
                    "flow": _FLOW_ZH_TO_EN[flow_zh],
                    "section_no": section_no,
                    "section_desc": section_desc,
                    "trade_value_usd": value,
                }
            )

    return pd.DataFrame(rows)


def load_taiwan_trade_by_section(use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    """載入財政部關務署「按HS類及主要國別(地區)分」進出口統計（本地快取，資料每月才更新一次，
    不需要每次都重新下載）。

    Returns:
        欄位：period, partner_group, flow, section_no, section_desc, trade_value_usd
    """
    if use_cache and not force_refresh and CACHE_PATH.exists():
        return pd.read_parquet(CACHE_PATH)

    raw_csv = _fetch_raw_csv()
    df = _parse_csv(raw_csv)

    if use_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(CACHE_PATH, index=False)
    return df


def get_reference_trade(
    section_no: int,
    partner_iso: str,
    flow: str = "Export",
    years: list[int] | None = None,
) -> pd.DataFrame:
    """查詢台灣官方(關務署)對某夥伴國所屬分組、某HS Section的進出口參考數字。

    Args:
        section_no: 見 data/hs_sections.py 的 hs_code_to_section()
        partner_iso: ISO3，會先轉成關務署的5個分組之一；不在分組內回傳空表
        flow: "Export" 或 "Import"
        years: 篩選年度，None則回傳全部可得年度

    Returns:
        欄位：period, partner_group, section_no, section_desc, trade_value_usd。
        查不到（例如partner_iso不在5個分組內）回傳空表。
    """
    partner_group = iso3_to_partner_group(partner_iso)
    if partner_group is None:
        return pd.DataFrame(
            columns=["period", "partner_group", "section_no", "section_desc", "trade_value_usd"]
        )

    df = load_taiwan_trade_by_section()
    result = df[
        (df["section_no"] == section_no) & (df["partner_group"] == partner_group) & (df["flow"] == flow)
    ]
    if years:
        result = result[result["period"].isin(years)]
    return result.sort_values("period")[
        ["period", "partner_group", "section_no", "section_desc", "trade_value_usd"]
    ].reset_index(drop=True)


def get_reference_trade_all_groups(
    section_no: int, flow: str = "Export", years: list[int] | None = None
) -> pd.DataFrame:
    """跟 get_reference_trade 一樣，但一次回傳全部5個官方分組（不需要先轉ISO3），
    用於「秀出台灣對這幾個主要市場的官方參考數字」這種總覽畫面。

    Returns:
        欄位同 get_reference_trade，可能同時有多個 partner_group 的列
    """
    df = load_taiwan_trade_by_section()
    result = df[(df["section_no"] == section_no) & (df["flow"] == flow)]
    if years:
        result = result[result["period"].isin(years)]
    return result.sort_values(["partner_group", "period"])[
        ["period", "partner_group", "section_no", "section_desc", "trade_value_usd"]
    ].reset_index(drop=True)
