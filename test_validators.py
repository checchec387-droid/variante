"""Tests for data validation and canonical unit normalization."""
import pytest
from src.core.models import CanonicalUnit, QuantityCategory, normalize_unit
from src.io.validators import (
    ValidationReport,
    validate_quantity_row,
    validate_unit,
    validate_variant_metadata,
)


def test_unit_normalization():
    """Vérifie la normalisation des variantes orthographiques d'unités routières."""
    assert normalize_unit("m3") == CanonicalUnit.CUBIC_METER.value
    assert normalize_unit("m³") == CanonicalUnit.CUBIC_METER.value
    assert normalize_unit("cum") == CanonicalUnit.CUBIC_METER.value

    assert normalize_unit("m2") == CanonicalUnit.SQUARE_METER.value
    assert normalize_unit("m²") == CanonicalUnit.SQUARE_METER.value
    assert normalize_unit("sqm") == CanonicalUnit.SQUARE_METER.value

    assert normalize_unit("ml") == CanonicalUnit.LINEAR_METER.value
    assert normalize_unit("m.l.") == CanonicalUnit.LINEAR_METER.value

    assert normalize_unit("t") == CanonicalUnit.TON.value
    assert normalize_unit("tonne") == CanonicalUnit.TON.value
    assert normalize_unit("tonnes") == CanonicalUnit.TON.value

    assert normalize_unit("u") == CanonicalUnit.UNIT.value
    assert normalize_unit("unité") == CanonicalUnit.UNIT.value
    assert normalize_unit("unite") == CanonicalUnit.UNIT.value

    # Rejet des unités non supportées ou erronées
    with pytest.raises(ValueError):
        normalize_unit("miles")

    with pytest.raises(ValueError):
        normalize_unit("invalide_unit_xyz")


def test_validate_quantity_row_valid():
    """Vérifie la validation d'une ligne de métré conforme."""
    report = ValidationReport()
    row = {
        "code": "couche_roulement",
        "designation": "BBSG 0/10",
        "categorie": "CHAUSSEE",
        "quantite": "12500.5",
        "unite": "m²",
    }
    item = validate_quantity_row(row, 1, report)

    assert report.is_valid
    assert item is not None
    assert item.code == "couche_roulement"
    assert item.quantity == 12500.5
    assert item.unit == "m2"
    assert item.category == QuantityCategory.CHAUSSEE


def test_validate_quantity_row_negative_value():
    """Vérifie le rejet d'une quantité négative."""
    report = ValidationReport()
    row = {
        "code": "deblai",
        "designation": "Déblai",
        "quantite": -50.0,
        "unite": "m3",
    }
    item = validate_quantity_row(row, 2, report)

    assert not report.is_valid
    assert item is None
    assert any("Quantité négative interdite" in err for err in report.errors)


def test_validate_quantity_row_invalid_unit():
    """Vérifie le rejet d'une unité inconnue."""
    report = ValidationReport()
    row = {
        "code": "fosses",
        "designation": "Fossé",
        "quantite": 100.0,
        "unite": "inconnu_xyz",
    }
    item = validate_quantity_row(row, 3, report)

    assert not report.is_valid
    assert item is None
    assert any("Unité invalide" in err for err in report.errors)


def test_validate_variant_metadata_checks():
    """Vérifie la détection d'erreurs sur les métadonnées de tracé."""
    report = ValidationReport()
    # Nom manquant
    meta = validate_variant_metadata({"nom": ""}, report)
    assert not report.is_valid
    assert meta is None

    # Longueur négative
    report2 = ValidationReport()
    meta2 = validate_variant_metadata({"nom": "V1", "longueur_m": -150.0}, report2)
    assert not report2.is_valid
    assert meta2 is None

    # Métadonnées valides
    report3 = ValidationReport()
    meta3 = validate_variant_metadata(
        {"nom": "Variante Test", "longueur_m": 3500.0, "emprise_m2": 70000.0},
        report3
    )
    assert report3.is_valid
    assert meta3 is not None
    assert meta3.name == "Variante Test"
    assert meta3.total_length_m == 3500.0
    assert meta3.right_of_way_m2 == 70000.0
