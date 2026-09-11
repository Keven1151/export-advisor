import pandas as pd

from analysis.competitor_analysis import competitor_ranking, price_comparison


def _raw_import_df():
    return pd.DataFrame(
        {
            "period": [2023, 2023, 2023],
            "reporter_iso": ["VNM", "VNM", "VNM"],
            "partner_iso": ["TWN", "CHN", "KOR"],
            "hs_code": ["854231"] * 3,
            "trade_value_usd": [300.0, 600.0, 100.0],
            "net_weight_kg": [10.0, 30.0, 5.0],
        }
    )


def test_competitor_ranking_computes_rank_and_share(fake_client_factory):
    client = fake_client_factory({("VNM", None, "M"): _raw_import_df()})

    ranking = competitor_ranking(client, "854231", "VNM", years=[2023])

    chn_row = ranking[ranking["partner_iso"] == "CHN"].iloc[0]
    assert chn_row["rank"] == 1
    assert chn_row["market_share_pct"] == 60.0

    twn_row = ranking[ranking["partner_iso"] == "TWN"].iloc[0]
    assert twn_row["rank"] == 2
    assert twn_row["market_share_pct"] == 30.0


def test_price_comparison_only_includes_taiwan_and_top_competitors(fake_client_factory):
    client = fake_client_factory({("VNM", None, "M"): _raw_import_df()})
    ranking = competitor_ranking(client, "854231", "VNM", years=[2023])

    price_df = price_comparison(ranking, _raw_import_df(), reporter_iso="TWN", top_n_competitors=1)

    countries = set(price_df["partner_iso"])
    assert countries == {"TWN", "CHN"}  # KOR 排名第3，top_n=1只取CHN，但台灣一定要有
    chn_price = price_df[price_df["partner_iso"] == "CHN"]["unit_price_usd_per_kg"].iloc[0]
    assert chn_price == 20.0
