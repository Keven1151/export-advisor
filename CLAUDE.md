# 專案慣例

完整需求見 [PRD.md](PRD.md)。

## 資料欄位命名（所有模組輸出的 DataFrame 統一使用這些欄位名）

- `period` (int, 例如 2024)：資料年度
- `reporter_iso` / `partner_iso`：ISO3 國碼（例如 TWN, VNM, USA）
- `hs_code` (str, 6 碼)：一律用字串保留前導零，不用 int
- `hs_version` (str)：`H5` = HS2022, `H4` = HS2017, `H3` = HS2012（對應 Comtrade classification code）
- `trade_flow` (str)：`Export` / `Import`
- `trade_value_usd` (float)
- `net_weight_kg` (float, 可為 NaN)

## HS Code 規則

- 分析與比對一律用 **HS 6 碼**，不處理各國 8-10 碼細目
- 任何介面或報告只要輸出 HS code 建議，必須附上免責提示（見 PRD §4）
- 版本換算不自行推斷，缺對照表時寧可標示「無法比對」也不要猜

## 重要：Comtrade 資料中的台灣代碼

UN Comtrade 使用數字國碼（對應 UN M49 標準），**不是 ISO3**。台灣因非聯合國會員，在 Comtrade
系統中並非用一般認知的碼別，而是被歸在 **reporterCode/partnerCode = 490「Other Asia, nes」**
這個類別下（且此類別可能混有其他未分類地區的資料，非台灣獨有）。這是使用 Comtrade 資料分析
台灣貿易時最容易出錯的地方，`data/country_codes.py` 已把 `TWN` 對應到 `490` 並在註解中標註，
任何查詢台灣為 reporter 或 partner 的地方都要留意此限制，必要時在畫面上提醒使用者「台灣資料
可能包含其他未分類地區，建議與財政部關務署數字交叉比對」。

**更重要的一點（2026-09-11 實測確認）**：台灣（reporterCode=490）在 Comtrade 裡的資料
**一律是 `isReported=false`**——也就是說台灣從來不是「自行申報」的數字，全部都是用貿易
夥伴國回報的鏡射資料（mirror data）推算出來的估計值（`isAggregate=true`、
`legacyEstimationFlag` 非0）。這代表：
1. 台灣的數字精確度/即時性通常比其他有自行申報的國家（如美、日、韓）差
2. 在「全球出口國排名」類的分析（`analysis/global_trade.py`）裡，台灣的排名可能被低估，
   因為鏡射推算本來就容易漏算/低估
3. `data/comtrade_client.py` 的 `_normalize()` 已經把原始 API 的 `isReported` 欄位保留成
   `is_reported` 欄位，未來如果要做「資料可信度」篩選或標註，直接用這欄位，不用再去猜

**實務後果（2026-10-22 使用者回報）**：因為台灣常常擠不進全球前N大排名，`analysis/global_trade.py`
裡任何「只回傳前N大」的函式（`world_exporter_ranking`、`world_importer_ranking`、舊版
`exporter_scorecard`）都曾經發生「台灣這個工具主要是給台灣企業用，但查詢結果卻完全看不到
台灣」的問題。修法是幫這些函式加一個 `always_include` 參數（`_country_ranking` 內部實作），
不管排名多少、只要查得到任何資料（含鏡射估計）就強制把該國加進結果，`app.py` 呼叫時一律傳
`always_include=exporter_iso`。**之後任何新的「列出前N大XX」類功能，都要照這個模式處理**，
不要只回傳單純截斷的前N名，不然同樣的問題會再發生一次。

### 用財政部關務署數字做粗略交叉比對（`data/mof_customs_client.py`）

為了讓使用者能大概判斷「Comtrade對台灣的估計值準不準」，加了一個獨立的資料源查財政部
關務署的官方（自行申報）數字，見 `data/mof_customs_client.py` + `data/hs_sections.py`。
**這不是精確替代**，用之前務必記住三個限制：
1. 官方公開資料集（data.gov.tw 28573）最細只到 **HS Section（19類，比HS2碼章別還粗，
   例如84章機械+85章電機被合併成同一類）**，沒有HS 6碼層級，所以只能對到「大類」，
   不能對到 `854231` 這種精確碼
2. 只有 **5個官方夥伴分組**：中國大陸與香港（合併）、日本、韓國、美國、東協（10國合併），
   沒有其他國家、也沒有「全球總計」，所以沒辦法直接驗證 `exporter_scorecard` 的
   `world_share_pct`（那是全球總出口），只能當作「至少這幾個市場出口了這麼多」的下限參考
3. 這是財政部「財政統計資料庫」的CSV匯出網址（`web02.mof.gov.tw/njswww/webMain.aspx`），
   **沒有正式API、沒有文件**，網址參數是逆向工程 data.gov.tw 資料集28573頁面上列的下載連結
   得到的，網站改版隨時可能失效——遇到抓不到資料，先去 https://data.gov.tw/dataset/28573
   確認資源網址有沒有變

真正要「HS6碼×任意國家」精確對應台灣官方數字，目前沒有免費/穩定的API，只能：
(a) 手動去 portal.sw.nat.gov.tw 的互動查詢工具查、或 (b) 付費跟關務署統計室買原始資料
（02-25505500 分機2336 / sta@customs.gov.tw）。這兩個都不適合寫進自動化pipeline，
所以目前就是把這個「粗略交叉比對」當作輔助參考，顯示在畫面上（`app.py` 的
`render_mof_reference`，只有選台灣當出口國時才會顯示），不是精確數字。

### 用 WTO 數字做更準確的「總額」交叉比對（`data/wto_client.py`，2026-10-22加入）

台灣雖然不是聯合國會員，但**是WTO正式會員**（會籍名稱 "Chinese Taipei"，reporter
code 158），WTO規定會員國要自行提交貿易統計給WTO的Integrated Database，所以這裡
查到的是**台灣官方真實申報數字，不是鏡射估計值**。實測2022年「Total merchandise」
出口 = 4,778億美元，跟已知的台灣真實出口數字幾乎完全吻合，比Comtrade準確很多。

**限制**：這個API的貿易「金額」指標只有**全球總額**，沒有國別拆分（查不到「出口到
越南多少」），能拆國別的只有「關稅稅率」指標（不是貿易金額），已實測確認過
（`p=704`查越南夥伴回傳空陣列）。品項分類用WTO自己的「SITC3 (aggregates)」約18類，
不是HS碼，兩者對照表在 `data/wto_product_groups.py`，**只有HS84/85(機械/電子)
做了HS4碼層級的細分對應（台灣出口大宗），其他類別只到HS2碼章別、或完全沒把握時
落到"MA"(製成品)這個大分類**，用的時候要看 `hs_code_to_wto_product()` 回傳的
confidence欄位（heading/chapter/rough），不要當作精確分類。

**用法分工**：WTO數字拿來驗證「台灣這個產品的全球總出口值對不對」最準；要看「出口到
特定國家多少」還是得靠 Comtrade（連帶其鏡射估計限制）或財政部關務署的5個官方分組
（`render_mof_reference`）。三個資料源在 `app.py` 的「出口國優劣勢分析」分頁一起顯示。

免費key申請：https://apiportal.wto.org/ 註冊 → Products > Standard 訂閱（免費，
10 calls/sec，每小時上限10000次）→ 設定 `WTO_API_KEY` 環境變數。沒設定這個key時
`render_wto_reference` 只會顯示一行提示文字，不影響其他功能。

## API / 環境變數

- `COMTRADE_API_KEY`：UN Comtrade subscription key，存在 `.env`（已加入 .gitignore），程式從環境變數讀取，絕不寫死在程式碼
- `WTO_API_KEY`：WTO Timeseries API subscription key，一樣存在 `.env`，見上面「用WTO數字」那段。沒設定時 `WTOClient.is_configured` 是 `False`，`get_chinese_taipei_trade()` 直接回傳空表，不拋例外
- Comtrade 免費層級速率限制：約 10 calls/min、500 calls/day → `data/comtrade_client.py` 必須做本地 parquet 快取，同一組 (hs_code, reporter, partner, period) 不重複呼叫
- `get_trade_data` 的 `reporter_iso` 和 `partner_iso` 都可以傳 `None`：
  - `reporter_iso=None` = 依所有申報國分列（用於「全球出口/進口國排名」，見 `analysis/global_trade.py`）
  - `partner_iso=None` = 依所有夥伴國分列（用於「某目標國的競爭國排名」，見 `analysis/competitor_analysis.py`）
  - 兩者不要同時傳 None，資料量會是完整雙邊貿易矩陣
- 免費 preview 端點（無key）一次只接受 1 個 period，`get_trade_data` 內部會逐年查詢；
  有 key 的正式端點一次可以查多個 period（逗號分隔），`get_trade_data` 會直接合併成一次呼叫，
  不要為了「保險」又改回逐年查，會讓有 key 時的查詢變慢很多
- 節流間隔：`MIN_SECONDS_BETWEEN_CALLS_PREVIEW` (6.5秒) / `MIN_SECONDS_BETWEEN_CALLS_WITH_KEY` (1.5秒)，
  依 `client.using_preview` 自動切換，官方沒有明確公告免費key的精確速率上限，這兩個數字是保守估計
- **實測結果（2026-09-11）**：有key時的429限制是「短時間爆量」觸發，不是穩定的每分鐘上限——
  連續呼叫約15-16次後開始429，官方回傳訊息通常是 `"Try again in 1 seconds"`，過1秒左右就恢復正常。
  所以 `data/comtrade_client.py` 的 `_call_api` 遇到429不是直接讓整個查詢失敗，而是用退避重試
  （2秒、4秒、8秒、16秒，共4次），這對「優劣勢分析」「建議目標國」這種一次要查十幾二十次API的
  分頁很重要，不然常常會因為短暫爆量就整頁失敗

## 快取

- 快取檔存於 `cache/`（已加入 .gitignore，不進版控）
- 快取 key 用 `{reporter}_{partner}_{hs_code}_{period}_{flow}.parquet` 命名

## 其他

- 所有金額單位一律 USD，不做幣別轉換假設
- 測試用 `pytest`，跑不到真實 API 時用 `tests/fixtures/` 下的樣本資料，不要在單元測試中打真實 API
