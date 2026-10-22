"""外銷市場分析與 HS Code 建議工具 — Streamlit Dashboard（見 PRD.md）。

執行：streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import plotly.express as px

from data.comtrade_client import ComtradeClient
from data.country_codes import ISO3_TO_COMTRADE, TAIWAN_ISO3
from data.hs_sections import hs_code_to_section
from data.mof_customs_client import get_reference_trade_all_groups
from analysis.trend_analysis import default_years
from analysis.global_trade import world_exporter_ranking, world_importer_ranking, exporter_scorecard
from analysis.competitor_analysis import competitor_ranking, price_comparison
from recommendation.hs_suggester import load_hs_reference, find_candidate_hs_codes, suggest_hs_codes
from recommendation.market_recommender import recommend_target_markets

st.set_page_config(page_title="外銷市場分析工具", layout="wide")

HS_DISCLAIMER = (
    "⚠️ HS code 相關內容僅為初步篩選建議，正式報關 / 產證申請前，"
    "請務必洽專業報關業者確認 6 碼以下細目。"
)
TAIWAN_CODE_NOTE = (
    "ℹ️ UN Comtrade 資料中，台灣（TWN）因非聯合國會員，被歸在 reporterCode/partnerCode "
    "= 490「Other Asia, nes」下，該分類可能包含其他未分類地區資料，非台灣獨有。"
    "**台灣的數字從來不是自行申報，全部是用貿易夥伴國的鏡射資料推算出來的估計值**，"
    "精確度與即時性可能不如美、日、韓等自行申報的國家，「全球出口國排名」中台灣的名次"
    "可能因此被低估。建議與財政部關務署官方統計交叉比對。"
)


@st.cache_resource
def get_client() -> ComtradeClient:
    return ComtradeClient()


@st.cache_data(ttl=86400)
def cached_hs_reference() -> pd.DataFrame:
    return load_hs_reference()


def run_query(state_key: str, params: tuple, clicked: bool, compute):
    """按下按鈕才查詢，結果存進 session_state，之後畫面重新整理（調滑桿、按下載等）
    只要查詢條件沒變就沿用，不會消失。API 失敗時顯示提示而不是整頁報錯。
    """
    if clicked:
        try:
            st.session_state[state_key] = (params, compute())
        except Exception as exc:  # noqa: BLE001 - 網路/429/API錯誤都轉成畫面提示
            st.session_state.pop(state_key, None)
            st.error(
                f"查詢失敗：{exc}\n\n"
                "若為 429 Too Many Requests，代表 Comtrade 短時間請求過多，"
                "請等約 1 分鐘再按一次（已查過的資料有快取，不會重複消耗額度）。"
            )
            return None
    saved = st.session_state.get(state_key)
    if saved and saved[0] == params:
        return saved[1]
    return None


def country_selectbox(label: str, key: str, default_iso: str | None = None) -> str:
    options = sorted(c for c in ISO3_TO_COMTRADE if c != "WLD")
    index = options.index(default_iso) if default_iso in options else 0
    return st.selectbox(label, options, index=index, key=key)


def resolve_hs_code() -> str | None:
    """側欄的產品輸入：可以直接輸入HS 6碼，或輸入產品描述後從候選清單挑一個。"""
    st.subheader("產品")
    query = st.text_input(
        "輸入 HS 6碼，或用文字描述產品（建議英文關鍵字，比對官方品名效果較好）",
        value=st.session_state.get("product_query", "854231"),
        key="product_query",
    )
    stripped = query.strip()

    if stripped.isdigit() and len(stripped) == 6:
        st.caption(f"以 HS code **{stripped}** 查詢")
        return stripped

    if not stripped:
        return None

    with st.spinner("比對候選 HS code 中..."):
        reference = cached_hs_reference()
        candidates = find_candidate_hs_codes(stripped, reference, top_n=8)

    if candidates.empty:
        st.warning("找不到相近的HS code，請換個關鍵字試試。")
        return None

    options = [f"{row.hs_code} - {row.description}" for row in candidates.itertuples()]
    choice = st.selectbox("請從候選HS code中選一個", options, key="hs_candidate_choice")
    return choice.split(" - ")[0]


def main() -> None:
    client = get_client()

    st.title("外銷市場分析與 HS Code 建議工具")
    if client.using_preview:
        st.info(
            "目前未設定 COMTRADE_API_KEY，使用 Comtrade 免費 preview 端點"
            "（結果上限500筆，且一次只能查一年，僅供試跑）。正式使用請至 comtradeplus.un.org "
            "申請免費金鑰，並填入 .env 的 COMTRADE_API_KEY。"
        )
    st.caption(TAIWAN_CODE_NOTE)

    with st.sidebar:
        hs_code = resolve_hs_code()
        st.divider()
        st.header("查詢條件")
        exporter_iso = country_selectbox("你的出口國（通常是台灣）", "exporter", TAIWAN_ISO3)
        n_years = st.slider("查詢近幾年", min_value=3, max_value=10, value=5)
        years = default_years(n_years)
        st.caption(f"查詢年度：{years[0]}–{years[-1]}")

    if not hs_code:
        st.info("請先在左側輸入產品描述或HS 6碼。")
        return

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 進出口趨勢", "⚖️ 出口國優劣勢分析", "🎯 建議出口目標國", "🔎 HS Code 建議"]
    )

    with tab1:
        render_trend_tab(client, hs_code, exporter_iso, years)

    with tab2:
        render_scorecard_tab(client, hs_code, exporter_iso, years)

    with tab3:
        render_target_market_tab(client, hs_code, exporter_iso, years)

    with tab4:
        render_hs_suggestion_tab(client, exporter_iso, years)


def render_trend_tab(client, hs_code, exporter_iso, years):
    st.subheader(f"HS {hs_code} 全球出口國 / 進口國趨勢")
    st.caption("出口國排名＝誰在賣這個產品；進口國排名＝誰在買，也是潛在目標市場的候選清單。")

    clicked = st.button("查詢趨勢", key="trend_btn")
    with st.spinner("查詢中..."):
        result = run_query(
            "trend_result", (hs_code, tuple(years), exporter_iso), clicked,
            lambda: (
                world_exporter_ranking(client, hs_code, years, top_n=10, always_include=exporter_iso),
                world_importer_ranking(client, hs_code, years, top_n=10, always_include=exporter_iso),
            ),
        )
    if result is not None:
        exporters, importers = result

        if exporters.empty and importers.empty:
            st.warning("查無資料，請確認 HS code / 年度是否正確。")
            return

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**全球主要出口國趨勢**")
            if exporters.empty:
                st.caption("查無出口資料")
            else:
                fig = px.line(
                    exporters, x="period", y="trade_value_usd", color="reporter_iso", markers=True,
                    title="出口值 (USD)", color_discrete_map={exporter_iso: "#FF4136"},
                )
                fig.for_each_trace(
                    lambda t: t.update(line=dict(width=4)) if t.name == exporter_iso else None
                )
                st.plotly_chart(fig, use_container_width=True)
                latest = exporters[exporters["period"] == exporters["period"].max()]
                st.dataframe(
                    latest[["reporter_iso", "trade_value_usd", "world_share_pct", "rank"]]
                    .sort_values("rank"),
                    use_container_width=True,
                )

        with col2:
            st.markdown("**全球主要進口市場趨勢**")
            if importers.empty:
                st.caption("查無進口資料")
            else:
                fig2 = px.line(
                    importers, x="period", y="trade_value_usd", color="reporter_iso", markers=True,
                    title="進口值 (USD)", color_discrete_map={exporter_iso: "#FF4136"},
                )
                fig2.for_each_trace(
                    lambda t: t.update(line=dict(width=4)) if t.name == exporter_iso else None
                )
                st.plotly_chart(fig2, use_container_width=True)
                latest2 = importers[importers["period"] == importers["period"].max()]
                st.dataframe(
                    latest2[["reporter_iso", "trade_value_usd", "world_share_pct", "rank"]]
                    .sort_values("rank"),
                    use_container_width=True,
                )

        # 不管台灣排不排得進前10大，只要查得到資料都會強制顯示在圖表裡（紅色粗線標示），
        # 這裡只處理「連資料都查不到」的情況
        exporter_in_list = exporter_iso in set(exporters.get("reporter_iso", []))
        if not exporter_in_list:
            st.caption(
                f"（{exporter_iso} 在 Comtrade 上完全查無這個HS code的出口資料，"
                "可能是真的沒有出口、或這項產品在Comtrade分類下沒有被記錄到，"
                "建議用財政部關務署數字或業界實務經驗交叉確認）"
            )


def render_scorecard_tab(client, hs_code, exporter_iso, years):
    st.subheader(f"HS {hs_code} 主要出口國優劣勢比較")
    top_n = st.slider("比較前幾大出口國", min_value=5, max_value=15, value=8, key="scorecard_topn")

    def compute_scorecard():
        ranking = world_exporter_ranking(client, hs_code, years, top_n=top_n)
        if ranking.empty:
            return None
        latest_period = ranking["period"].max()
        exporter_isos = ranking[ranking["period"] == latest_period]["reporter_iso"].tolist()
        if exporter_iso not in exporter_isos:
            exporter_isos.append(exporter_iso)
        return exporter_scorecard(client, hs_code, exporter_isos, years=years)

    clicked = st.button("產生優劣勢比較", key="scorecard_btn")
    with st.spinner("查詢中（每個國家還要查一次出口目的地分布，會比較久）..."):
        scorecard = run_query(
            "scorecard_result", (hs_code, exporter_iso, tuple(years), top_n), clicked, compute_scorecard
        )
    if clicked and scorecard is None and "scorecard_result" in st.session_state:
        st.warning("查無資料，請確認 HS code / 年度是否正確。")
    if scorecard is not None:
        if scorecard.empty:
            st.warning("查無資料。")
            return

        st.caption(
            "world_share_pct=全球出口市占；export_cagr=出口值成長率；"
            "avg_unit_price_usd_per_kg=平均單價（僅供定位參考，非品質判斷）；"
            "destination_hhi=出口目的地集中度(越低越分散)；destination_count=有出口記錄的市場數"
        )
        st.dataframe(
            scorecard.style.apply(
                lambda row: ["background-color: #2b4a6f" if row["reporter_iso"] == exporter_iso else "" for _ in row],
                axis=1,
            ),
            use_container_width=True,
        )

        # plotly的size屬性不吃NaN（某些國家可能查不到目的地分布），畫圖前補值，
        # 不影響 st.dataframe 顯示的原始 scorecard（缺值就是缺值，不要在資料表裡面造假）
        plot_df = scorecard.copy()
        plot_df["destination_count_for_plot"] = plot_df["destination_count"].fillna(
            plot_df["destination_count"].median()
        ).fillna(1)

        fig = px.scatter(
            plot_df, x="export_cagr", y="world_share_pct", size="destination_count_for_plot",
            color=(plot_df["reporter_iso"] == exporter_iso).map({True: "你的出口國", False: "其他出口國"}),
            text="reporter_iso", title="成長率 vs 全球市占（泡泡大小＝出口市場數）",
        )
        fig.update_traces(textposition="top center")
        fig.update_xaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

        if exporter_iso == TAIWAN_ISO3:
            render_mof_reference(hs_code, years)


def render_mof_reference(hs_code: str, years: list[int]) -> None:
    """財政部關務署官方參考數字，用來粗略交叉比對Comtrade對台灣的估計值準不準
    （見 CLAUDE.md「台灣代碼」那段：Comtrade台灣數字一律是非自行申報的鏡射估計值）。
    """
    section_no, section_desc = hs_code_to_section(hs_code)
    with st.expander(f"🔎 台灣官方參考數字（財政部關務署，HS Section {section_no}「{section_desc}」）"):
        st.caption(
            "⚠️ 關務署公開資料只到「類」這個層級（比HS2碼章別更粗，"
            f"HS {hs_code} 所屬的「{section_desc}」這一類包含好幾個HS章別，不是精確對應"
            f"{hs_code}本身），而且只有5個官方分組（中國大陸與香港、日本、韓國、美國、東協）、"
            "沒有全球總計。這裡只能拿來看「量級和成長方向對不對」，不能當作精確數字。"
        )
        ref = get_reference_trade_all_groups(section_no, flow="Export", years=years)
        if ref.empty:
            st.caption("查無官方參考資料。")
            return

        fig = px.line(
            ref, x="period", y="trade_value_usd", color="partner_group", markers=True,
            title=f"台灣出口「{section_desc}」到5大官方分組市場的官方申報金額 (USD)",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(ref, use_container_width=True)


def render_target_market_tab(client, hs_code, exporter_iso, years):
    st.subheader(f"HS {hs_code} 建議出口目標國")
    n_candidates = st.slider("從全球前幾大進口市場中評估", min_value=5, max_value=15, value=8, key="target_n")

    clicked = st.button("產生目標國建議", key="target_btn")
    with st.spinner("查詢並評分中（候選市場越多、耗時越久）..."):
        outcome = run_query(
            "target_result", (hs_code, exporter_iso, tuple(years), n_candidates), clicked,
            lambda: recommend_target_markets(
                client, hs_code, exporter_iso=exporter_iso, years=years, n_candidates=n_candidates
            ),
        )
    if outcome is not None:
        result, disclaimer = outcome
        if result.empty:
            st.warning("查無資料，請確認 HS code / 年度是否正確。")
            return

        st.caption(disclaimer)
        st.caption(
            "target_score=綜合評分(0-100)；import_cagr=市場進口成長率；"
            "exporter_share_pct=你目前在該市場的市占；supplier_hhi=供應商集中度(越低越好切入)；"
            "price_advantage_pct=你的單價相對當地前5大供應國中位數的優勢(正值＝較便宜)"
        )
        st.dataframe(result, use_container_width=True)

        fig = px.bar(
            result, x="target_country_iso", y="target_score", title="目標市場綜合評分排序",
        )
        st.plotly_chart(fig, use_container_width=True)

        csv = result.to_csv(index=False).encode("utf-8-sig")
        st.download_button("下載 CSV", csv, file_name=f"target_markets_{hs_code}.csv")


def render_hs_suggestion_tab(client, exporter_iso, years):
    st.subheader("HS Code 拓銷建議")
    st.caption("跟上面三個分頁不同：這裡是「給定一個目標國，幫你找值得評估的HS code」。")
    st.caption(HS_DISCLAIMER)

    product_desc = st.text_input(
        "產品描述（建議用英文關鍵字，比對 Comtrade 官方品名效果較好）",
        placeholder="例如：aluminum bicycle frame",
        key="hs_suggest_desc",
    )
    target_country = country_selectbox("目標國", "hs_target", "VNM")

    clicked = st.button("產生建議", key="hs_btn") and bool(product_desc.strip())
    with st.spinner("比對候選 HS code 並查詢市場資料中（可能需要一段時間）..."):
        outcome = run_query(
            "hs_result", (product_desc.strip(), target_country, exporter_iso, tuple(years)), clicked,
            lambda: suggest_hs_codes(
                client, product_desc, target_country, reporter_iso=exporter_iso, years=years
            ),
        )
    if outcome is not None:
        scored, disclaimer = outcome
        if scored.empty:
            st.warning("查無合適候選碼，請嘗試更具體的英文關鍵字。")
            return

        st.dataframe(scored, use_container_width=True)
        st.caption(disclaimer)

        csv = scored.to_csv(index=False).encode("utf-8-sig")
        st.download_button("下載 CSV", csv, file_name=f"hs_suggestions_{target_country}.csv")


if __name__ == "__main__":
    main()
