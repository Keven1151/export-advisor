import json
from pathlib import Path

import data.comtrade_client as comtrade_client_module
from data.comtrade_client import ComtradeClient

FIXTURE = Path(__file__).parent / "fixtures" / "comtrade_raw_sample.json"


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {"data": []}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_normalize_maps_fields_correctly():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    df = ComtradeClient._normalize(raw)

    assert list(df["period"]) == [2022, 2023]
    assert list(df["reporter_iso"]) == ["VNM", "VNM"]
    assert list(df["partner_iso"]) == ["TWN", "TWN"]
    assert list(df["hs_code"]) == ["854231", "854231"]
    assert df["trade_value_usd"].iloc[1] == 1200000.0
    assert df["net_weight_kg"].iloc[0] == 5000.0
    assert bool(df["is_reported"].iloc[0]) is True


def test_normalize_empty_input_returns_empty_df_with_expected_columns():
    df = ComtradeClient._normalize([])
    assert df.empty
    assert "trade_value_usd" in df.columns


def test_cache_path_uses_all_label_for_none_partner(tmp_path):
    client = ComtradeClient(api_key="dummy", cache_dir=tmp_path)
    path = client._cache_path("VNM", None, "854231", "2023", "M")
    assert "ALL" in path.name


def test_using_preview_when_no_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("COMTRADE_API_KEY", raising=False)
    client = ComtradeClient(api_key=None, cache_dir=tmp_path)
    assert client.using_preview is True

    client2 = ComtradeClient(api_key="some-key", cache_dir=tmp_path)
    assert client2.using_preview is False


def test_call_api_retries_on_429_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(comtrade_client_module.time, "sleep", lambda _seconds: None)
    responses = [_FakeResponse(429), _FakeResponse(429), _FakeResponse(200, {"data": [{"period": "2023"}]})]
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(1)
        return responses[len(calls) - 1]

    monkeypatch.setattr(comtrade_client_module.requests, "get", fake_get)

    client = ComtradeClient(api_key="dummy", cache_dir=tmp_path)
    result = client._call_api("VNM", "WLD", "854231", "2023", "X", "HS")

    assert result == [{"period": "2023"}]
    assert len(calls) == 3


def test_call_api_raises_after_exhausting_retries_on_429(tmp_path, monkeypatch):
    monkeypatch.setattr(comtrade_client_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        comtrade_client_module.requests, "get", lambda *a, **k: _FakeResponse(429)
    )

    client = ComtradeClient(api_key="dummy", cache_dir=tmp_path)
    try:
        client._call_api("VNM", "WLD", "854231", "2023", "X", "HS")
        assert False, "應該要raise RuntimeError"
    except RuntimeError as e:
        assert "429" in str(e)
