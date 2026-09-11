import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeComtradeClient:
    """假的 ComtradeClient，測試分析邏輯時不打真實 API（見 CLAUDE.md 測試規則）。

    依 (reporter_iso, partner_iso, flow) 對照表回傳事先準備好的 DataFrame。
    """

    def __init__(self, responses: dict[tuple, pd.DataFrame]):
        self.responses = responses
        self.calls: list[dict] = []

    def get_trade_data(self, reporter_iso, partner_iso, hs_code, period, flow="M", **kwargs):
        self.calls.append(
            {
                "reporter_iso": reporter_iso,
                "partner_iso": partner_iso,
                "hs_code": hs_code,
                "period": period,
                "flow": flow,
            }
        )
        key = (reporter_iso, partner_iso, flow)
        return self.responses.get(key, pd.DataFrame())


@pytest.fixture
def fake_client_factory():
    return FakeComtradeClient
