"""Tests for Autodesk Civil 3D export parser."""
import io
import pytest
from src.io.civil3d_parser import parse_civil3d_volume_report, parse_station_to_meters


def test_parse_station_to_meters():
    """Vérifie la conversion des chaînages/PKs routiers Civil 3D."""
    assert parse_station_to_meters("0+000.00") == 0.0
    assert parse_station_to_meters("0+250.50") == 250.50
    assert parse_station_to_meters("1+450.00") == 1450.00
    assert parse_station_to_meters("12+000.00") == 12000.00
    assert parse_station_to_meters("750.25") == 750.25


def test_parse_civil3d_volume_report_cumulative():
    """Vérifie le parsing d'un export de cubatures Civil 3D avec colonnes cumulées."""
    c3d_csv = """Station,Cut Area (Sq.m),Fill Area (Sq.m),Cut Vol (Cu.m),Fill Vol (Cu.m),Cum. Cut Vol (Cu.m),Cum. Fill Vol (Cu.m)
0+000.00,10.0,0.0,0.0,0.0,0.0,0.0
0+100.00,15.0,2.0,1250.0,100.0,1250.0,100.0
0+250.00,20.0,5.0,2625.0,525.0,3875.0,625.0
0+500.00,0.0,30.0,2500.0,4375.0,6375.0,5000.0
"""
    stream = io.StringIO(c3d_csv)
    variant, report = parse_civil3d_volume_report(stream, variant_name="Variante Axe C3D", file_type="csv")

    assert report.is_valid
    assert variant.name == "Variante Axe C3D"
    assert variant.metadata.total_length_m == 500.0  # de 0+000.00 à 0+500.00
    assert variant.get_quantity("deblai_civil3d") == 6375.0
    assert variant.get_quantity("remblai_civil3d") == 5000.0


def test_parse_civil3d_volume_report_incremental():
    """Vérifie le calcul par somme des volumes incrémentaux si pas de colonne cumulée."""
    c3d_csv = """Station;Cut Vol;Fill Vol
100;500;200
200;800;150
300;300;650
"""
    stream = io.StringIO(c3d_csv)
    variant, report = parse_civil3d_volume_report(stream, variant_name="Variante Incrémentale", file_type="csv")

    assert report.is_valid
    assert variant.metadata.total_length_m == 200.0  # 300 - 100
    assert variant.get_quantity("deblai_civil3d") == 1600.0  # 500 + 800 + 300
    assert variant.get_quantity("remblai_civil3d") == 1000.0  # 200 + 150 + 650
