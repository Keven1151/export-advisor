import pytest

from data.hs_sections import hs_code_to_section


def test_electronics_chapter_maps_to_machinery_electrical_section():
    section_no, desc = hs_code_to_section("854231")
    assert section_no == 16
    assert desc == "機械及電機設備"


def test_first_chapter_maps_to_section_one():
    assert hs_code_to_section("010110")[0] == 1


def test_last_chapter_maps_to_other_section():
    assert hs_code_to_section("970100")[0] == 19


def test_boundary_between_sections():
    # 83章(基本金屬製品, 第15類) vs 84章(機械, 第16類) 剛好是類別交界
    assert hs_code_to_section("830000")[0] == 15
    assert hs_code_to_section("840000")[0] == 16


def test_invalid_hs_code_raises():
    with pytest.raises(ValueError):
        hs_code_to_section("ABCDEF")
