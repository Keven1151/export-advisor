import pytest

from data.wto_product_groups import hs_code_to_wto_product


def test_integrated_circuits_maps_to_heading_level():
    code, name, confidence = hs_code_to_wto_product("854231")
    assert code == "MAMTOTIC"
    assert name == "Integrated circuits and electronic components"
    assert confidence == "heading"


def test_computers_maps_to_heading_level():
    code, name, confidence = hs_code_to_wto_product("847130")
    assert code == "MAMTOTEP"
    assert confidence == "heading"


def test_generic_chapter_84_falls_back_to_machinery():
    # 不在 _HS_HEADING_OVERRIDE 裡的84章號別，應該落到機械及運輸設備這個較粗的分類
    code, name, confidence = hs_code_to_wto_product("840810")
    assert code == "MAMT"
    assert confidence == "chapter"


def test_automotive_chapter_maps_correctly():
    code, name, confidence = hs_code_to_wto_product("870321")
    assert code == "MAMTAU"
    assert confidence == "chapter"


def test_unmapped_chapter_falls_back_to_manufactures():
    code, name, confidence = hs_code_to_wto_product("940360")  # 家具，沒有特別對應
    assert code == "MA"
    assert confidence == "rough"


def test_invalid_hs_code_raises():
    with pytest.raises(ValueError):
        hs_code_to_wto_product("AB")
