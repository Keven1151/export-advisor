import pandas as pd

from recommendation.market_recommender import recommend_target_markets


def _partner_breakdown(period, rows):
    """rows: list of (partner_iso, trade_value_usd, net_weight_kg)"""
    return pd.DataFrame(
        {
            "period": [period] * len(rows),
            "partner_iso": [r[0] for r in rows],
            "trade_value_usd": [r[1] for r in rows],
            "net_weight_kg": [r[2] for r in rows],
        }
    )


def test_recommend_target_markets_ranks_growing_accessible_market_higher(fake_client_factory):
    world_import_ranking_df = pd.DataFrame(
        {
            "period": [2022, 2022, 2023, 2023],
            "reporter_iso": ["VNM", "IDN", "VNM", "IDN"],
            "trade_value_usd": [800.0, 200.0, 1000.0, 202.0],
            "net_weight_kg": [80.0, 20.0, 100.0, 20.0],
        }
    )

    vnm_2023_partners = _partner_breakdown(
        2023, [("CHN", 600.0, 60.0), ("TWN", 150.0, 20.0), ("KOR", 250.0, 20.0)]
    )
    idn_2023_partners = _partner_breakdown(2023, [("CHN", 200.0, 20.0), ("TWN", 2.0, 0.2)])

    responses = {
        (None, "WLD", "M"): world_import_ranking_df,
        ("VNM", "WLD", "M"): pd.DataFrame(
            {"period": [2022, 2023], "trade_value_usd": [800.0, 1000.0], "net_weight_kg": [80.0, 100.0]}
        ),
        ("IDN", "WLD", "M"): pd.DataFrame(
            {"period": [2022, 2023], "trade_value_usd": [200.0, 202.0], "net_weight_kg": [20.0, 20.0]}
        ),
        ("TWN", "VNM", "X"): pd.DataFrame(
            {"period": [2022, 2023], "trade_value_usd": [100.0, 150.0], "net_weight_kg": [10.0, 20.0]}
        ),
        ("TWN", "IDN", "X"): pd.DataFrame(
            {"period": [2022, 2023], "trade_value_usd": [2.0, 2.0], "net_weight_kg": [0.2, 0.2]}
        ),
        ("VNM", None, "M"): vnm_2023_partners,
        ("IDN", None, "M"): idn_2023_partners,
    }
    client = fake_client_factory(responses)

    result, disclaimer = recommend_target_markets(
        client, "854231", exporter_iso="TWN", years=[2022, 2023], n_candidates=5
    )

    assert set(result["target_country_iso"]) == {"VNM", "IDN"}
    assert disclaimer  # 免責提示文字不應該是空的

    vnm_row = result[result["target_country_iso"] == "VNM"].iloc[0]
    idn_row = result[result["target_country_iso"] == "IDN"].iloc[0]

    # VNM市場成長快、供應商較分散(3家)、台灣單價比中位數便宜 -> 應該排名/分數都高於 IDN
    assert result.iloc[0]["target_country_iso"] == "VNM"
    assert vnm_row["target_score"] > idn_row["target_score"]
    assert vnm_row["import_cagr"] > idn_row["import_cagr"]
    assert vnm_row["supplier_hhi"] < idn_row["supplier_hhi"]
