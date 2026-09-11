from pathlib import Path

import pandas as pd
import pytest

import data.mof_customs_client as mof_module
from data.mof_customs_client import (
    _parse_csv,
    iso3_to_partner_group,
    get_reference_trade,
    get_reference_trade_all_groups,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mof_customs_sample.csv"


def test_iso3_to_partner_group_known_and_unknown():
    assert iso3_to_partner_group("USA") == "美國"
    assert iso3_to_partner_group("HKG") == "中國大陸與香港"
    assert iso3_to_partner_group("VNM") == "東協"
    assert iso3_to_partner_group("DEU") is None  # 不在5個分組內


def test_parse_csv_converts_roc_year_and_units_and_skips_monthly_rows():
    raw = FIXTURE.read_text(encoding="utf-8-sig")
    df = _parse_csv(raw)

    # 110年 1月 這種月資料要被濾掉，只留年度彙總
    assert set(df["period"]) == {2021, 2022}  # 110+1911=2021, 111+1911=2022

    row = df[
        (df["period"] == 2021)
        & (df["partner_group"] == "美國")
        & (df["flow"] == "Export")
        & (df["section_no"] == 16)
    ]
    assert len(row) == 1
    # 原始CSV單位是千美元(1500)，轉成美元要*1000
    assert row["trade_value_usd"].iloc[0] == 1_500_000


def test_parse_csv_keeps_total_row_with_section_no_zero():
    raw = FIXTURE.read_text(encoding="utf-8-sig")
    df = _parse_csv(raw)

    total_row = df[
        (df["period"] == 2021)
        & (df["partner_group"] == "中國大陸與香港")
        & (df["flow"] == "Import")
        & (df["section_no"] == 0)
    ]
    assert len(total_row) == 1
    assert total_row["trade_value_usd"].iloc[0] == 1_000_000


def test_get_reference_trade_filters_by_section_partner_flow_and_years(monkeypatch):
    raw = FIXTURE.read_text(encoding="utf-8-sig")
    fake_df = _parse_csv(raw)
    monkeypatch.setattr(mof_module, "load_taiwan_trade_by_section", lambda *a, **k: fake_df)

    result = get_reference_trade(section_no=16, partner_iso="USA", flow="Export", years=[2021, 2022])

    assert list(result["period"]) == [2021, 2022]
    assert list(result["trade_value_usd"]) == [1_500_000, 1_700_000]


def test_get_reference_trade_returns_empty_for_unmapped_country(monkeypatch):
    raw = FIXTURE.read_text(encoding="utf-8-sig")
    fake_df = _parse_csv(raw)
    monkeypatch.setattr(mof_module, "load_taiwan_trade_by_section", lambda *a, **k: fake_df)

    result = get_reference_trade(section_no=16, partner_iso="DEU", flow="Export")
    assert result.empty


def test_get_reference_trade_all_groups_returns_every_partner(monkeypatch):
    raw = FIXTURE.read_text(encoding="utf-8-sig")
    fake_df = _parse_csv(raw)
    monkeypatch.setattr(mof_module, "load_taiwan_trade_by_section", lambda *a, **k: fake_df)

    result = get_reference_trade_all_groups(section_no=16, flow="Export", years=[2021])

    assert set(result["partner_group"]) == {"中國大陸與香港", "美國"}
