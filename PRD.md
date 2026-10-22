# 外銷市場分析與 HS Code 建議工具 — 產品需求文件 (PRD)

## 1. 背景與目標

協助台灣外銷企業回答三個核心問題：

1. 我的產品出口到目標國，過去的量值趨勢與台灣市占率如何？
2. 在目標國市場，我的主要競爭國是誰？他們的市占、價格、成長速度如何？
3. 如果我想拓銷新產品到某個目標國，哪些 HS code（品項）值得優先評估？

工具定位是**初步篩選與決策輔助**，不取代報關業者或專業貿易顧問的判斷，尤其 HS code
歸類具有法律與關務效力，所有建議都必須明確標示「初步建議，需專業複核」。

## 2. 使用者與情境

- 主要使用者：外銷業務、市場開發人員（非資料分析背景，需要簡單好懂的介面）
- 典型情境：業務手上有一批 HS code（既有出口品項），想知道要主推哪個國家；或已鎖定目標國，
  想知道該推哪些品項、目前誰在跟台灣競爭

## 3. 資料來源

| 來源 | 用途 | 存取方式 | 限制 |
|---|---|---|---|
| UN Comtrade (comtradeapi.un.org) | 全球進出口統計（依 HS code + 國家 + 年度） | API，需免費申請 subscription key | 免費層級約 500 calls/day、10 calls/min，需快取 |
| WITS (World Bank) | 關稅稅率、貿易障礙 | API / 資料下載 | 之後版本再整合 |
| 財政部關務署貿易統計查詢網 | 台灣官方出口統計，作為 Comtrade 資料交叉驗證 | 網站查詢，暫無公開 API | 之後版本視需要建置 |

MVP 先完成 UN Comtrade 串接，其餘來源列為 v2 待辦（見 §7）。

## 4. HS Code 版本規則

- 統一以 **HS 6 碼**（國際共通碼）作為分析與比對層級，避免各國 HS 8-10 碼細目不一致的問題
- 資料需標註來源年度對應的 HS 版本（HS2012 / HS2017 / HS2022），跨版本比較時使用 Comtrade
  提供的版本轉換表，不自行猜測對應關係
- 所有輸出畫面與報告，只要出現 HS code，一律附註：「本建議為初步篩選，正式報關 / 產證申請
  前請洽專業報關業者確認 6 碼以下細目」

## 5. 功能範圍（MVP，2026-09-11 改為「產品優先」的全球視角架構）

使用者一開始先決定「產品」（輸入 HS 6碼，或輸入文字描述後從候選清單挑一個，
見 `recommendation/hs_suggester.py` 的 `find_candidate_hs_codes`），之後四個分頁都圍繞
同一個 HS code 做分析，不再要求使用者一開始就指定「目標國」——目標國本身也是
分析輸出之一（見 F4）。

### F1. 進出口趨勢分析（全球視角）
- 輸入：HS 6碼（或文字描述解析出的HS code）、年份區間（預設近 5 年）
- 輸出：
  - 全球主要**出口國**排名與歷年趨勢（誰在賣這個產品）
  - 全球主要**進口市場**排名與歷年趨勢（誰在買，也是 F4 候選目標國的來源）
- 對應程式：`analysis/global_trade.py` 的 `world_exporter_ranking` / `world_importer_ranking`

### F2. 出口國優劣勢分析
- 輸入：HS 6碼、要比較的出口國清單（預設抓全球前N大 + 使用者自己的出口國）
- 輸出每個出口國：全球市占、出口值成長率(CAGR)、平均單價（定位參考）、
  出口目的地集中度(HHI，越低越分散、風險越低)、出口目的地數量
- 對應程式：`analysis/global_trade.py` 的 `exporter_scorecard`

### F3. 建議出口目標國
- 輸入：HS 6碼、使用者的出口國（預設台灣）
- 邏輯：從 F1 的全球進口市場排名取候選目標國 → 對每個候選查市場成長率、市場規模、
  使用者現有市占、供應商集中度(HHI)、使用者相對當地前5大供應國的單價優劣 → 綜合評分排序
- 輸出：目標國清單 + 評分明細 + 免責提示（僅供優先順序參考，不含關稅/法規）
- 對應程式：`recommendation/market_recommender.py` 的 `recommend_target_markets`

### F4. HS Code 拓銷建議（給定目標國，找值得推的HS code——跟 F1-F3 反過來的方向）
- 輸入：產品文字描述（中/英文）、公司既有 HS code 清單（選填）、目標國
- 邏輯：文字比對出候選 HS code → 查詢目標國進口成長率、競爭集中度 (HHI)、可得的關稅資訊
  → 綜合評分排序
- 輸出：候選 HS code 清單 + 評分理由 + 免責提示
- 對應程式：`recommendation/hs_suggester.py`

### F5. Dashboard
- Streamlit 單頁應用：側欄輸入產品(HS碼/描述)+出口國+年份 → 四個分頁（F1/F2/F3/F4）
  → 各分頁可匯出 CSV

## 6. 非目標（MVP 不做）

- 不做使用者帳號 / 多租戶權限
- 不做關稅稅則以外的法規遵循檢查（如檢驗檢疫、標籤法規）
- 不做即時報價或供應商媒合

## 7. 待辦 / v2 規劃

- 整合 WITS 關稅資料到 HS code 評分邏輯
- ~~整合財政部關務署資料做台灣出口數字交叉驗證~~ 2026-09-11 已完成粗略版本
  （`data/mof_customs_client.py`，只到HS Section層級+5個官方分組，見 CLAUDE.md 說明）
- ~~找更準確的台灣官方貿易數字來源~~ 2026-10-22 已完成：WTO Timeseries API
  （`data/wto_client.py`），台灣是WTO正式會員，這是真實申報數字不是估計值，
  但只有全球總額、沒有國別拆分，精確到HS6碼×任意國家目前還是沒有免費穩定API
- FTA / 經貿協議關稅優惠納入評分
- 多語系介面（英文版供海外業務使用）

## 8. 技術棧

- Python 3.11+
- 資料層：`requests` + `pandas` + 本地 parquet 快取
- 分析層：`pandas` / `numpy`
- 介面：Streamlit
- 測試：`pytest`
- 部署：Docker

## 9. 專案結構

```
產品外銷工具/
├── PRD.md
├── CLAUDE.md              # 專案慣例（欄位命名、HS版本、API key設定）
├── requirements.txt
├── .env.example
├── data/
│   ├── comtrade_client.py     # UN Comtrade API 串接 + 快取
│   ├── country_codes.py       # ISO3 <-> Comtrade數字碼對照
│   ├── mof_customs_client.py  # 財政部關務署官方數字（粗略交叉比對用，見CLAUDE.md限制）
│   ├── hs_sections.py         # HS章別(2碼) -> HS Section(19類)對照，關務署資料查詢用
│   ├── wto_client.py          # WTO官方申報貿易總額（台灣真實數字，但無國別拆分）
│   └── wto_product_groups.py  # HS碼 -> WTO品項分類(SITC3彙總)對照
├── analysis/
│   ├── trend_analysis.py     # 雙邊(某出口國->某目標國)趨勢、市占率、CAGR等共用工具函式
│   ├── competitor_analysis.py# 給定目標國，看該國進口來源國排名(F4用)
│   └── global_trade.py       # 不限定目標國，看全球出口/進口國排名與優劣勢(F1/F2用)
├── recommendation/
│   ├── hs_suggester.py        # F4：給定目標國，建議HS code
│   └── market_recommender.py  # F3：給定HS code，建議目標國
├── app.py                 # Streamlit dashboard
├── tests/
└── cache/                 # 本地 parquet 快取（.gitignore）
```
