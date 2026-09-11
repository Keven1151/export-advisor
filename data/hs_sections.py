"""HS 章別(2碼) <-> HS Section(WCO標準21類，本專案交叉比對用財政部關務署的19類版本，
把很少用的第19-21類合併成「其他」) 對照表。

用途：財政部關務署的開放資料只做到「類」這個很粗的層級（見 data/mof_customs_client.py），
沒有到HS 6碼，所以要把使用者查詢的HS 6碼往上對應到所屬的「類」，才能去查關務署的官方數字
做粗略的量級交叉比對（見 CLAUDE.md 對這個交叉比對限制的說明）。
"""

from __future__ import annotations

# (章別起, 章別訖, 類別編號, 類別中文名稱) —— 跟關務署開放資料集(data.gov.tw 28573)的
# 19類名稱逐字對應，第19類「其他」合併了WCO標準的第19-21類(軍火、雜項製品、藝術品)
_SECTION_RANGES: list[tuple[int, int, int, str]] = [
    (1, 5, 1, "活動物；動物產品"),
    (6, 14, 2, "植物產品"),
    (15, 15, 3, "動植物油脂"),
    (16, 24, 4, "調製食品；飲料及菸酒"),
    (25, 27, 5, "礦產品"),
    (28, 38, 6, "化學品"),
    (39, 40, 7, "塑膠、橡膠及其製品"),
    (41, 43, 8, "毛皮及其製品"),
    (44, 46, 9, "木及木製品"),
    (47, 49, 10, "紙漿；紙及其製品；印刷品"),
    (50, 63, 11, "紡織品"),
    (64, 67, 12, "鞋、帽及其他飾品"),
    (68, 70, 13, "非金屬礦物製品"),
    (71, 71, 14, "珠寶及貴金屬製品"),
    (72, 83, 15, "基本金屬及其製品"),
    (84, 85, 16, "機械及電機設備"),
    (86, 89, 17, "運輸工具"),
    (90, 92, 18, "光學及精密儀器；鐘錶；樂器"),
    (93, 99, 19, "其他"),
]


def hs_code_to_section(hs_code: str) -> tuple[int, str]:
    """HS 6碼(或任意長度、只要前2碼是章別)轉成所屬的關務署19類編號+中文名稱。

    Args:
        hs_code: 至少前2碼是HS章別的字串，例如 "854231" -> 章別85

    Returns:
        (section_no, section_desc)，例如 (16, "機械及電機設備")

    Raises:
        ValueError: HS code格式不對（前2碼不是1-99的數字）
    """
    chapter_str = hs_code[:2]
    if not chapter_str.isdigit():
        raise ValueError(f"無法從 '{hs_code}' 解析出HS章別（前2碼應為數字）")
    chapter = int(chapter_str)

    for start, end, section_no, section_desc in _SECTION_RANGES:
        if start <= chapter <= end:
            return section_no, section_desc

    raise ValueError(f"HS章別 {chapter} 超出已知範圍(1-99)")
