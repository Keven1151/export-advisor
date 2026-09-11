import pandas as pd

from analysis.trend_analysis import cagr, export_trend, market_share


def test_cagr_basic():
    df = pd.DataFrame({"period": [2020, 2023], "trade_value_usd": [100.0, 133.1]})
    result = cagr(df)
    assert result is not None
    assert round(result, 3) == 0.100  # 100 -> 133.1 over 3 years ≈ 10%/yr


def test_cagr_insufficient_data_returns_none():
    df = pd.DataFrame({"period": [2023], "trade_value_usd": [100.0]})
    assert cagr(df) is None


def test_cagr_zero_start_value_returns_none():
    df = pd.DataFrame({"period": [2020, 2023], "trade_value_usd": [0.0, 100.0]})
    assert cagr(df) is None


def test_export_trend_computes_yoy(fake_client_factory):
    reporter_df = pd.DataFrame(
        {
            "period": [2022, 2023],
            "reporter_iso": ["TWN", "TWN"],
            "partner_iso": ["VNM", "VNM"],
            "hs_code": ["854231", "854231"],
            "trade_value_usd": [100.0, 150.0],
            "net_weight_kg": [10.0, 12.0],
        }
    )
    client = fake_client_factory({("TWN", "VNM", "X"): reporter_df})

    result = export_trend(client, "854231", "VNM", reporter_iso="TWN", years=[2022, 2023])

    assert pd.isna(result["yoy_growth"].iloc[0])
    assert result["yoy_growth"].iloc[1] == 0.5


def test_market_share_divides_reporter_by_world_import(fake_client_factory):
    reporter_df = pd.DataFrame(
        {"period": [2023], "trade_value_usd": [200.0], "net_weight_kg": [5.0]}
    )
    world_df = pd.DataFrame(
        {"period": [2023], "trade_value_usd": [1000.0], "net_weight_kg": [50.0]}
    )
    client = fake_client_factory(
        {("TWN", "VNM", "X"): reporter_df, ("VNM", "WLD", "M"): world_df}
    )

    result = market_share(client, "854231", "VNM", reporter_iso="TWN", years=[2023])

    assert result["market_share_pct"].iloc[0] == 20.0
