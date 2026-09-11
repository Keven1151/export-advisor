# 外銷市場分析與 HS Code 建議工具

協助台灣外銷企業分析目標市場進出口趨勢、競爭國，並提供 HS code 拓銷建議的 MVP。
完整需求見 [PRD.md](PRD.md)，專案慣例（欄位命名、台灣代碼注意事項等）見 [CLAUDE.md](CLAUDE.md)。

## 快速開始

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # 填入 COMTRADE_API_KEY（沒有key也能跑，會自動用preview端點）
streamlit run app.py
```

## 申請免費 Comtrade API Key

1. 到 https://comtradeplus.un.org/ 註冊帳號
2. 登入後在 API Management 頁面申請 subscription key
3. 填入 `.env` 的 `COMTRADE_API_KEY`

沒有申請 key 也能直接執行，工具會自動改用 Comtrade 的免費 preview 端點
（結果上限 500 筆，僅供先試跑流程）。

## 跑測試

```bash
pytest
```

測試全部用假資料（`tests/fixtures/`、`FakeComtradeClient`），不會打真實 API。

## 已知限制（MVP 階段）

- 只做到 HS 6 碼層級的分析，不處理各國 8-10 碼細目
- 台灣在 Comtrade 資料中沒有獨立國碼，被歸在 reporterCode/partnerCode=490
  「Other Asia, nes」下，可能混有其他未分類地區資料，介面已加註提醒
- 尚未整合關稅稅率 (WITS)、FTA 優惠、財政部關務署資料，見 PRD.md §7 待辦
- HS code 建議僅為初步篩選，不具報關效力
