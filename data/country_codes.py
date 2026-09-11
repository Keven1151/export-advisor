"""ISO3 alpha 國碼 <-> UN Comtrade 數字國碼（UN M49 標準）對照表。

Comtrade 的 reporterCode / partnerCode 一律是數字碼，不是 ISO3。這裡只收錄台灣外銷
業務常用的市場，需要新國家時直接補進 `ISO3_TO_COMTRADE` 即可（可從
https://comtradeapi.un.org/files/v1/app/reference/Reporters.json 查完整清單）。

重要：台灣 (TWN) 因非聯合國會員，在 Comtrade 裡沒有獨立代碼，資料被歸在
reporterCode/partnerCode = 490「Other Asia, nes」底下，且該分類可能包含其他未分類
地區的資料，並非台灣獨有。使用台灣作為 reporter 或 partner 查詢時，畫面上一定要
提醒使用者這個限制，並建議與財政部關務署官方統計交叉比對。
"""

from __future__ import annotations

TAIWAN_ISO3 = "TWN"
TAIWAN_COMTRADE_CODE = "490"  # "Other Asia, nes" — 非台灣專屬代碼，使用時務必附註說明

# ISO3 -> Comtrade reporter/partner 數字碼（字串，Comtrade API 兩種都接受，統一用字串）
ISO3_TO_COMTRADE: dict[str, str] = {
    "TWN": TAIWAN_COMTRADE_CODE,
    "WLD": "0",  # World / 全球彙總，常用來當作 partner 查全世界進口
    "CHN": "156",
    "USA": "842",
    "JPN": "392",
    "KOR": "410",
    "VNM": "704",
    "THA": "764",
    "IDN": "360",
    "MYS": "458",
    "PHL": "608",
    "SGP": "702",
    "IND": "699",
    "DEU": "276",
    "FRA": "251",
    "GBR": "826",
    "ITA": "381",
    "NLD": "528",
    "ESP": "724",
    "POL": "616",
    "MEX": "484",
    "BRA": "76",
    "CAN": "124",
    "AUS": "36",
    "NZL": "554",
    "TUR": "792",
    "SAU": "682",
    "ARE": "784",
    "ZAF": "710",
    "EGY": "818",
    "RUS": "643",
    "HKG": "344",
    "MAC": "446",
    "KHM": "116",
    "MMR": "104",
    "LAO": "418",
    "BGD": "50",
    "PAK": "586",
}

COMTRADE_TO_ISO3: dict[str, str] = {v: k for k, v in ISO3_TO_COMTRADE.items() if k != "WLD"}


def to_comtrade_code(iso3: str) -> str:
    """ISO3 轉 Comtrade 數字碼；查不到就丟出明確錯誤，不要靜默回傳錯誤資料。"""
    iso3 = iso3.upper().strip()
    if iso3 not in ISO3_TO_COMTRADE:
        raise KeyError(
            f"'{iso3}' 尚未收錄在 ISO3_TO_COMTRADE，請到 "
            "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json 查代碼後補進 data/country_codes.py"
        )
    return ISO3_TO_COMTRADE[iso3]


def to_iso3(comtrade_code: str) -> str | None:
    """Comtrade 數字碼轉 ISO3，查不到回傳 None（保留原始碼供顯示，不要拋例外中斷整批資料處理）。"""
    return COMTRADE_TO_ISO3.get(str(comtrade_code).strip())
