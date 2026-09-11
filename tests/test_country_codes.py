import pytest

from data.country_codes import to_comtrade_code, to_iso3, TAIWAN_COMTRADE_CODE


def test_taiwan_maps_to_490():
    assert to_comtrade_code("TWN") == TAIWAN_COMTRADE_CODE == "490"


def test_round_trip():
    assert to_iso3(to_comtrade_code("VNM")) == "VNM"


def test_unknown_iso3_raises():
    with pytest.raises(KeyError):
        to_comtrade_code("ZZZ")


def test_unknown_comtrade_code_returns_none():
    assert to_iso3("999999") is None
