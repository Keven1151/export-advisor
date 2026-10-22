import data.wto_client as wto_module
from data.wto_client import WTOClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


_SAMPLE_DATASET = {
    "Dataset": [
        {
            "ProductOrSectorCode": "TO",
            "ProductOrSector": "Total merchandise",
            "Year": 2023,
            "Value": 479000.0,
        },
        {
            "ProductOrSectorCode": "MAMTOTIC",
            "ProductOrSector": "Integrated circuits and electronic components",
            "Year": 2023,
            "Value": 198000.0,
        },
    ]
}


def test_get_chinese_taipei_trade_normalizes_units_to_usd(tmp_path, monkeypatch):
    monkeypatch.setattr(
        wto_module.requests, "get", lambda *a, **k: _FakeResponse(_SAMPLE_DATASET)
    )
    client = WTOClient(api_key="dummy", cache_dir=tmp_path)

    df = client.get_chinese_taipei_trade("X", years=[2023])

    total_row = df[df["product_code"] == "TO"].iloc[0]
    assert total_row["trade_value_usd"] == 479_000_000_000.0  # 百萬美元 -> 美元
    ic_row = df[df["product_code"] == "MAMTOTIC"].iloc[0]
    assert ic_row["trade_value_usd"] == 198_000_000_000.0


def test_returns_empty_df_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("WTO_API_KEY", raising=False)
    client = WTOClient(api_key=None, cache_dir=tmp_path)
    assert client.is_configured is False

    df = client.get_chinese_taipei_trade("X", years=[2023])

    assert df.empty
    assert list(df.columns) == ["period", "product_code", "product_name", "trade_value_usd"]


def test_caches_results_to_avoid_repeat_calls(tmp_path, monkeypatch):
    calls = []

    def fake_get(*a, **k):
        calls.append(1)
        return _FakeResponse(_SAMPLE_DATASET)

    monkeypatch.setattr(wto_module.requests, "get", fake_get)
    client = WTOClient(api_key="dummy", cache_dir=tmp_path)

    client.get_chinese_taipei_trade("X", years=[2023])
    client.get_chinese_taipei_trade("X", years=[2023])

    assert len(calls) == 1
