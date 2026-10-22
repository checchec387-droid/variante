"""Tests for Excel and CSV parsers for variants and unit cost catalogs."""
import io
import pandas as pd
import pytest
from src.core.models import QuantityCategory
from src.io.parsers import (
    DataParsingError,
    parse_cost_catalog,
    parse_multi_variant_matrix,
    parse_variant_csv,
    parse_variant_excel,
)


def test_parse_variant_csv_semicolon():
    """Vérifie le parsing d'un fichier CSV avec séparateur point-virgule et virgules décimales."""
    csv_data = """code;designation;categorie;quantite;unite
deblai_meuble;Déblai meuble;TERRASSEMENT;15000;m3
remblai;Remblai de chaussée;TERRASSEMENT;12000;m3
couche_bb;Béton Bitumineux;CHAUSSEE;8500.5;m²
"""
    stream = io.StringIO(csv_data)
    variant, report = parse_variant_csv(stream, default_name="Variante Test CSV")

    assert report.is_valid
    assert variant.name == "Variante Test CSV"
    assert variant.get_quantity("deblai_meuble") == 15000.0
    assert variant.get_quantity("remblai") == 12000.0
    assert variant.get_quantity("couche_bb") == 8500.5
    assert variant.items["couche_bb"].unit == "m2"


def test_parse_variant_excel_multisheet(tmp_path):
    """Vérifie le parsing d'un classeur Excel à deux onglets (Metadonnees + Quantites)."""
    file_path = tmp_path / "variante_complete.xlsx"

    # Création du classeur Excel en mémoire
    df_meta = pd.DataFrame([
        ["nom", "Variante Sud"],
        ["longueur_m", 4200.0],
        ["emprise_m2", 84000.0],
        ["foisonnement", 1.25],
        ["compactage", 0.92],
    ])

    df_qty = pd.DataFrame([
        {"code": "deblai", "designation": "Déblais généraux", "categorie": "TERRASSEMENT", "quantite": 55000.0, "unite": "m3"},
        {"code": "remblai", "designation": "Remblais généraux", "categorie": "TERRASSEMENT", "quantite": 48000.0, "unite": "m3"},
        {"code": "glissiere", "designation": "Glissière N2", "categorie": "EQUIPEMENT", "quantite": 3200.0, "unite": "ml"},
    ])

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        df_meta.to_excel(writer, sheet_name="Metadonnees", index=False, header=False)
        df_qty.to_excel(writer, sheet_name="Quantites", index=False)

    variant, report = parse_variant_excel(str(file_path))

    assert report.is_valid
    assert variant.name == "Variante Sud"
    assert variant.metadata.total_length_m == 4200.0
    assert variant.metadata.right_of_way_m2 == 84000.0
    assert variant.metadata.swelling_factor == 1.25
    assert variant.metadata.compaction_factor == 0.92
    assert variant.get_quantity("deblai") == 55000.0
    assert variant.get_quantity("glissiere") == 3200.0


def test_parse_multi_variant_matrix(tmp_path):
    """Vérifie le parsing d'une matrice comparant plusieurs variantes en colonnes."""
    file_path = tmp_path / "matrice_variantes.xlsx"

    df_matrix = pd.DataFrame([
        {
            "code": "deblai_meuble",
            "designation": "Déblai meuble",
            "categorie": "TERRASSEMENT",
            "unite": "m3",
            "Variante 1": 25000.0,
            "Variante 2": 18000.0,
        },
        {
            "code": "remblai",
            "designation": "Remblai",
            "categorie": "TERRASSEMENT",
            "unite": "m3",
            "Variante 1": 20000.0,
            "Variante 2": 22000.0,
        },
        {
            "code": "enrobe",
            "designation": "Couche de roulement",
            "categorie": "CHAUSSEE",
            "unite": "m2",
            "Variante 1": 15000.0,
            "Variante 2": 14000.0,
        },
    ])

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        df_matrix.to_excel(writer, sheet_name="Comparatif", index=False)

    variants, report = parse_multi_variant_matrix(str(file_path), file_type="excel")

    assert report.is_valid
    assert len(variants) == 2
    v1, v2 = variants[0], variants[1]
    assert "Variante 1" in v1.name
    assert "Variante 2" in v2.name
    assert v1.get_quantity("deblai_meuble") == 25000.0
    assert v2.get_quantity("deblai_meuble") == 18000.0
    assert v1.get_quantity("enrobe") == 15000.0
    assert v2.get_quantity("enrobe") == 14000.0


def test_parse_cost_catalog_csv():
    """Vérifie le chargement d'un bordereau de prix unitaires depuis un CSV."""
    csv_bpu = """code;designation;unite;prix_unitaire
deblai_meuble;Déblai meuble;m3;6.50
remblai;Remblai;m3;8.20
enrobe;BBSG;m2;14.50
"""
    stream = io.StringIO(csv_bpu)
    catalog, report = parse_cost_catalog(stream, file_type="csv", currency="EUR")

    assert report.is_valid
    assert catalog.currency == "EUR"
    assert catalog.get_price("deblai_meuble") == 6.50
    assert catalog.get_price("remblai") == 8.20
    assert catalog.get_price("enrobe") == 14.50
    assert catalog.get_price("inconnu") is None


def test_parse_variant_missing_columns():
    """Vérifie le rejet d'un fichier avec colonnes obligatoires manquantes."""
    csv_incomplet = """code;valeur
deblai;1000
"""
    stream = io.StringIO(csv_incomplet)
    with pytest.raises(DataParsingError) as exc_info:
        parse_variant_csv(stream)
    assert "manquantes" in str(exc_info.value)
