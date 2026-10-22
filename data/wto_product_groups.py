"""HS碼 -> WTO貿易統計使用的「SITC3 (aggregates)」品項分類對照表。

WTO Timeseries API 的貿易「金額」類指標（merchandise exports/imports by product group）
用的不是HS碼，是WTO自己的一套約18類品項分類（`data/wto_client.py` 的
`load_product_categories()` 可以查到完整清單）。這套分類沒有官方公布的HS逐碼對照表，
這裡是根據類別名稱與國際貿易常識建的**概略對照**，電子零組件/機械類（台灣出口大宗）
特別用HS 4碼(稅則號別)層級做了比較細的對應，其他類別只到HS 2碼(章別)層級、相對粗略。

跟 data/hs_sections.py 的差異：hs_sections.py 對應到財政部關務署用的19類(HS Section)，
這裡對應到WTO用的18類(SITC3彙總)，兩套分類完全不同，不要混用。
"""

from __future__ import annotations

# HS 4碼(稅則號別) -> WTO品項代碼。只收錄電子/機械類有把握的細分，
# 其餘HS84/85下的號別會fallback到MAMT(機械及運輸設備)這個較粗的上層分類
_HS_HEADING_OVERRIDE: dict[str, str] = {
    "8471": "MAMTOTEP",  # 電腦及周邊設備
    "8517": "MAMTOTTL",  # 電話機、通訊設備
    "8525": "MAMTOTTL",
    "8526": "MAMTOTTL",
    "8527": "MAMTOTTL",
    "8528": "MAMTOTTL",
    "8529": "MAMTOTTL",
    "8541": "MAMTOTIC",  # 二極體、電晶體等半導體元件
    "8542": "MAMTOTIC",  # 積體電路
}

# HS 2碼(章別) -> WTO品項代碼。沒特別標註的章別一律落到 "MA"(製成品)這個大分類，
# 不要假裝有更細的對應
_HS_CHAPTER_MAP: dict[int, str] = {
    **{ch: "AGFO" for ch in range(1, 25)},  # 01-24 食品、動植物
    25: "MI",  # 礦產品(鹽、石材等)
    26: "MI",  # 礦砂
    27: "MIFU",  # 燃料(煤、石油)
    **{ch: "MACH" for ch in range(28, 39)},  # 28-38 化學品
    30: "MACHPH",  # 藥品(覆蓋化學品的子分類)
    **{ch: "MATE" for ch in range(50, 61)},  # 50-60 紡織原料及製品
    61: "MACL",  # 針織成衣
    62: "MACL",  # 梭織成衣
    63: "MATE",
    72: "MAIS",  # 鋼鐵
    73: "MAIS",  # 鋼鐵製品
    84: "MAMT",  # 機械(細分見_HS_HEADING_OVERRIDE)
    85: "MAMT",  # 電機設備(細分見_HS_HEADING_OVERRIDE)
    86: "MAMTTE",  # 鐵道機車
    87: "MAMTAU",  # 車輛
    88: "MAMTTE",  # 航空器
    89: "MAMTTE",  # 船舶
}

_PRODUCT_CODE_NAMES: dict[str, str] = {
    "TO": "Total merchandise",
    "AG": "Agricultural products",
    "AGFO": "Food",
    "MI": "Fuels and mining products",
    "MIFU": "Fuels",
    "MA": "Manufactures",
    "MACH": "Chemicals",
    "MACHPH": "Pharmaceuticals",
    "MAIS": "Iron and steel",
    "MAMT": "Machinery and transport equipment",
    "MAMTOF": "Office and telecom equipment",
    "MAMTOTEP": "Electronic data processing and office equipment",
    "MAMTOTTL": "Telecommunications equipment",
    "MAMTOTIC": "Integrated circuits and electronic components",
    "MAMTTE": "Transport equipment",
    "MAMTAU": "Automotive products",
    "MATE": "Textiles",
    "MACL": "Clothing",
}


def hs_code_to_wto_product(hs_code: str) -> tuple[str, str, str]:
    """HS碼轉WTO品項代碼。

    Args:
        hs_code: HS 6碼字串

    Returns:
        (product_code, product_name, confidence)
        confidence: "heading" = HS4碼精確對應(電子/機械細項)；
                    "chapter" = HS2碼章別對應；
                    "rough" = 完全沒把握，落到MA(製成品)這個大分類

    Raises:
        ValueError: hs_code 格式不對
    """
    if len(hs_code) < 4 or not hs_code[:4].isdigit():
        raise ValueError(f"無法從 '{hs_code}' 解析出HS碼（至少前4碼要是數字）")

    heading = hs_code[:4]
    if heading in _HS_HEADING_OVERRIDE:
        code = _HS_HEADING_OVERRIDE[heading]
        return code, _PRODUCT_CODE_NAMES[code], "heading"

    chapter = int(hs_code[:2])
    if chapter in _HS_CHAPTER_MAP:
        code = _HS_CHAPTER_MAP[chapter]
        return code, _PRODUCT_CODE_NAMES[code], "chapter"

    return "MA", _PRODUCT_CODE_NAMES["MA"], "rough"
