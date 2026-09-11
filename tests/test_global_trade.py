import pandas as pd

from analysis.global_trade import world_exporter_ranking, world_importer_ranking, exporter_scorecard


def _world_export_df():
    return pd.DataFrame(
        {
            "period": [2022, 2022, 2022, 2023, 2023, 2023],
            "reporter_iso": ["USA", "CHN", "TWN", "USA", "CHN", "TWN"],
            "trade_value_usd": [500.0, 300.0, 200.0, 600.0, 250.0, 300.0],
            "net_weight_kg": [50.0, 40.0, 20.0, 55.0, 35.0, 25.0],
        }
    )


def test_world_exporter_ranking_computes_share_and_rank(fake_client_factory):
    client = fake_client_factory({(None, "WLD", "X"): _world_export_df()})

    ranking = world_exporter_ranking(client, "854231", years=[2022, 2023], top_n=15)

    latest = ranking[ranking["period"] == 2023]
    usa_row = latest[latest["reporter_iso"] == "USA"].iloc[0]
    assert usa_row["rank"] == 1
    assert round(usa_row["world_share_pct"], 2) == round(600 / (600 + 250 + 300) * 100, 2)


def test_world_exporter_ranking_keeps_full_history_for_current_top_n(fake_client_factory):
    client = fake_client_factory({(None, "WLD", "X"): _world_export_df()})

    ranking = world_exporter_ranking(client, "854231", years=[2022, 2023], top_n=2)

    # 2023最大兩國是USA, TWN（CHN在2023掉到第三），但TWN在2022的資料也該保留
    countries_2023 = set(ranking[ranking["period"] == 2023]["reporter_iso"])
    assert countries_2023 == {"USA", "TWN"}
    twn_periods = set(ranking[ranking["reporter_iso"] == "TWN"]["period"])
    assert twn_periods == {2022, 2023}


def test_world_importer_ranking_uses_import_flow(fake_client_factory):
    import_df = pd.DataFrame(
        {
            "period": [2023, 2023],
            "reporter_iso": ["VNM", "IDN"],
            "trade_value_usd": [400.0, 100.0],
            "net_weight_kg": [10.0, 5.0],
        }
    )
    client = fake_client_factory({(None, "WLD", "M"): import_df})

    ranking = world_importer_ranking(client, "854231", years=[2023])

    assert set(ranking["reporter_iso"]) == {"VNM", "IDN"}
    vnm_row = ranking[ranking["reporter_iso"] == "VNM"].iloc[0]
    assert vnm_row["world_share_pct"] == 80.0


def test_exporter_scorecard_computes_hhi_and_growth(fake_client_factory):
    responses = {
        (None, "WLD", "X"): _world_export_df(),
        ("USA", None, "X"): pd.DataFrame(
            {
                "period": [2023, 2023],
                "partner_iso": ["JPN", "KOR"],
                "trade_value_usd": [300.0, 300.0],
            }
        ),
        ("TWN", None, "X"): pd.DataFrame(
            {
                "period": [2023],
                "partner_iso": ["VNM"],
                "trade_value_usd": [300.0],
            }
        ),
    }
    client = fake_client_factory(responses)

    scorecard = exporter_scorecard(client, "854231", ["USA", "TWN"], years=[2022, 2023])

    usa_row = scorecard[scorecard["reporter_iso"] == "USA"].iloc[0]
    twn_row = scorecard[scorecard["reporter_iso"] == "TWN"].iloc[0]

    # USA出口分散在兩個市場各半 -> HHI = 50^2+50^2 = 5000；台灣全押一國 -> HHI=10000
    assert usa_row["destination_hhi"] == 5000.0
    assert twn_row["destination_hhi"] == 10000.0
    assert usa_row["destination_count"] == 2
    assert twn_row["destination_count"] == 1
    # 台灣出口值 200->300 是成長的
    assert twn_row["export_cagr"] > 0


def test_exporter_scorecard_finds_country_even_if_not_top_ranked(fake_client_factory):
    # 模擬台灣的實際情況：出口值遠低於前幾大出口國，如果 exporter_scorecard 內部
    # 用「只取前N大」的排名去查，會直接漏掉這種國家（見 CLAUDE.md 台灣資料估計值的說明）
    world_df = pd.DataFrame(
        {
            "period": [2023, 2023, 2023],
            "reporter_iso": ["USA", "CHN", "TWN"],
            "trade_value_usd": [5000.0, 4000.0, 1.0],
            "net_weight_kg": [500.0, 400.0, 0.1],
        }
    )
    client = fake_client_factory(
        {
            (None, "WLD", "X"): world_df,
            ("TWN", None, "X"): pd.DataFrame(
                {"period": [2023], "partner_iso": ["VNM"], "trade_value_usd": [1.0]}
            ),
        }
    )

    scorecard = exporter_scorecard(client, "854231", ["TWN"], years=[2023])

    assert list(scorecard["reporter_iso"]) == ["TWN"]
    assert scorecard.iloc[0]["world_share_pct"] < 1.0
