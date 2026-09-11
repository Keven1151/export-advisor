import pandas as pd

from recommendation.hs_suggester import _hhi, find_candidate_hs_codes, score_candidates


def test_hhi_single_dominant_supplier_is_high():
    shares = pd.Series([90.0, 5.0, 5.0])
    assert _hhi(shares) == 90**2 + 5**2 + 5**2


def test_hhi_empty_returns_none():
    assert _hhi(pd.Series([], dtype=float)) is None


def test_find_candidate_hs_codes_matches_by_description():
    reference = pd.DataFrame(
        {
            "hs_code": ["854231", "010110", "870120"],
            "description": [
                "854231 - Electronic integrated circuits; processors and controllers",
                "010110 - Pure-bred breeding animals",
                "870120 - Road tractors for semi-trailers",
            ],
        }
    )
    candidates = find_candidate_hs_codes("integrated circuit processor", reference, top_n=2)

    assert candidates.iloc[0]["hs_code"] == "854231"
    assert candidates.iloc[0]["similarity_score"] > 50


def test_score_candidates_ranks_higher_growth_and_lower_concentration_first(fake_client_factory):
    # HS A: 台灣出口成長快、目標國市場分散(HHI低) -> 應該排前面
    # HS B: 台灣出口沒成長、市場被單一國家壟斷(HHI高) -> 應該排後面
    class MultiHSFakeClient:
        def get_trade_data(self, reporter_iso, partner_iso, hs_code, period, flow="M", **kwargs):
            if flow == "X":
                # 台灣出口值本身不影響評分邏輯（只用來算市占分母以外的資料），維持不變即可
                return pd.DataFrame(
                    {"period": [2021, 2023], "trade_value_usd": [100.0, 100.0], "net_weight_kg": [1, 1]}
                )
            if partner_iso is None:
                # 依所有夥伴國分列（用於算HHI）：A 較分散、B 被單一國家壟斷
                if hs_code == "A":
                    partners, values = ["TWN", "VNM_LOCAL", "OTHER"], [40.0, 30.0, 30.0]
                else:
                    partners, values = ["CHN"], [100.0]
                return pd.DataFrame(
                    {
                        "period": [2023] * len(partners),
                        "partner_iso": partners,
                        "trade_value_usd": values,
                    }
                )
            # 目標國從全世界進口的總額（partner_iso == "WLD"）：A 成長快、B 持平
            world_values = [500.0, 700.0] if hs_code == "A" else [500.0, 500.0]
            return pd.DataFrame({"period": [2021, 2023], "trade_value_usd": world_values})

    client = MultiHSFakeClient()
    candidates = pd.DataFrame(
        {
            "hs_code": ["A", "B"],
            "description": ["desc a", "desc b"],
            "similarity_score": [90, 90],
        }
    )

    result = score_candidates(client, candidates, "VNM", reporter_iso="TWN", years=[2021, 2023])

    assert result.iloc[0]["hs_code"] == "A"
    assert result.iloc[0]["opportunity_score"] > result.iloc[1]["opportunity_score"]
