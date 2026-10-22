"""Edge case and stress audit tests for Road Variant Comparator."""
import io
import pytest
from src.core.calculator import (
    calculate_earthwork_balance,
    calculate_variant_total_cost,
    compare_variants,
    compute_relative_delta,
)
from src.core.models import (
    EarthworkStatus,
    QuantityCategory,
    QuantityItem,
    UnitCostCatalog,
    UnitPrice,
    Variant,
    VariantMetadata,
)
from src.io.parsers import (
    DataParsingError,
    parse_cost_catalog,
    parse_variant_csv,
)
from src.reporting.excel_exporter import generate_excel_report
from src.reporting.pdf_exporter import generate_pdf_report


def test_audit_zero_quantities_and_division_by_zero():
    """Audit du comportement avec des quantités rigoureusement nulles."""
    meta1 = VariantMetadata(name="V_Zero_Base", total_length_m=1000.0, right_of_way_m2=20000.0)
    meta2 = VariantMetadata(name="V_Zero_Target", total_length_m=1000.0, right_of_way_m2=20000.0)

    v1 = Variant(metadata=meta1)
    v2 = Variant(metadata=meta2)

    # Poste à 0 dans les deux
    v1.add_item(QuantityItem(code="deblai", designation="Déblai", quantity=0.0, unit="m3", category=QuantityCategory.TERRASSEMENT))
    v2.add_item(QuantityItem(code="deblai", designation="Déblai", quantity=0.0, unit="m3", category=QuantityCategory.TERRASSEMENT))

    # Poste à 0 dans base, positif dans cible
    v1.add_item(QuantityItem(code="remblai", designation="Remblai", quantity=0.0, unit="m3", category=QuantityCategory.TERRASSEMENT))
    v2.add_item(QuantityItem(code="remblai", designation="Remblai", quantity=500.0, unit="m3", category=QuantityCategory.TERRASSEMENT))

    # Poste positif dans base, à 0 dans cible
    v1.add_item(QuantityItem(code="bb", designation="Béton bitumineux", quantity=1000.0, unit="m2", category=QuantityCategory.CHAUSSEE))
    v2.add_item(QuantityItem(code="bb", designation="Béton bitumineux", quantity=0.0, unit="m2", category=QuantityCategory.CHAUSSEE))

    catalog = UnitCostCatalog(currency="EUR")
    catalog.add_price(UnitPrice(code="deblai", designation="Déblai", unit="m3", price=5.0))
    catalog.add_price(UnitPrice(code="remblai", designation="Remblai", unit="m3", price=8.0))
    catalog.add_price(UnitPrice(code="bb", designation="BB", unit="m2", price=12.0))

    comp = compare_variants(baseline=v1, target=v2, catalog=catalog)

    items_dict = {it.code: it for it in comp.items}

    # deblai : 0 -> 0 => delta = 0, delta% = 0.0
    assert items_dict["deblai"].delta_abs_qty == 0.0
    assert items_dict["deblai"].delta_rel_qty_percent == 0.0

    # remblai : 0 -> 500 => delta = +500, delta% = None (division par zéro évitée)
    assert items_dict["remblai"].delta_abs_qty == 500.0
    assert items_dict["remblai"].delta_rel_qty_percent is None

    # bb : 1000 -> 0 => delta = -1000, delta% = -100.0%
    assert items_dict["bb"].delta_abs_qty == -1000.0
    assert items_dict["bb"].delta_rel_qty_percent == -100.0

    # Vérification que les exports ne crashent pas avec ces cas limites
    excel_bytes = generate_excel_report(comp, v1, v2, catalog)
    assert len(excel_bytes) > 0

    pdf_bytes = generate_pdf_report(comp, v1, v2, catalog)
    assert pdf_bytes.startswith(b"%PDF-")


def test_audit_missing_prices_in_bpu():
    """Audit du comportement lorsque des prix manquent totalement ou partiellement."""
    meta1 = VariantMetadata(name="V1", total_length_m=1000.0, right_of_way_m2=20000.0)
    meta2 = VariantMetadata(name="V2", total_length_m=1000.0, right_of_way_m2=20000.0)

    v1 = Variant(metadata=meta1)
    v2 = Variant(metadata=meta2)

    v1.add_item(QuantityItem(code="item_connu", designation="Item 1", quantity=100.0, unit="m", category=QuantityCategory.DIVERS))
    v1.add_item(QuantityItem(code="item_inconnu", designation="Item 2", quantity=50.0, unit="m", category=QuantityCategory.DIVERS))

    v2.add_item(QuantityItem(code="item_connu", designation="Item 1", quantity=120.0, unit="m", category=QuantityCategory.DIVERS))
    v2.add_item(QuantityItem(code="item_inconnu", designation="Item 2", quantity=80.0, unit="m", category=QuantityCategory.DIVERS))

    # BPU ne contenant QUE item_connu
    catalog = UnitCostCatalog(currency="EUR")
    catalog.add_price(UnitPrice(code="item_connu", designation="Item 1", unit="m", price=10.0))

    total_cost, cat_costs, missing = calculate_variant_total_cost(v1, catalog)
    assert total_cost == 1000.0  # 100 * 10
    assert "item_inconnu" in missing

    comp = compare_variants(baseline=v1, target=v2, catalog=catalog)
    item_inc = next(it for it in comp.items if it.code == "item_inconnu")
    assert item_inc.unit_price is None
    assert item_inc.baseline_cost is None
    assert item_inc.target_cost is None
    assert item_inc.delta_abs_cost is None

    # Les exports doivent gérer proprement les cellules vides sans crash
    excel_bytes = generate_excel_report(comp, v1, v2, catalog)
    assert len(excel_bytes) > 0

    pdf_bytes = generate_pdf_report(comp, v1, v2, catalog)
    assert len(pdf_bytes) > 0


def test_audit_disjoint_variant_items():
    """Audit lorsque deux variantes n'ont absolument aucun poste en commun."""
    meta1 = VariantMetadata(name="V_Tranchée", total_length_m=1000.0, right_of_way_m2=15000.0)
    meta2 = VariantMetadata(name="V_Viaduc", total_length_m=900.0, right_of_way_m2=8000.0)

    v1 = Variant(metadata=meta1)
    v1.add_item(QuantityItem(code="deblai_rocher", designation="Déblai rocheux", quantity=50000.0, unit="m3", category=QuantityCategory.TERRASSEMENT))

    v2 = Variant(metadata=meta2)
    v2.add_item(QuantityItem(code="tablier_beton", designation="Tablier béton précontraint", quantity=4500.0, unit="m2", category=QuantityCategory.OUVRAGES_ART))

    comp = compare_variants(baseline=v1, target=v2)
    assert len(comp.items) == 2

    # Export Excel et PDF sur des variantes disjointes
    excel_bytes = generate_excel_report(comp, v1, v2)
    pdf_bytes = generate_pdf_report(comp, v1, v2)

    assert len(excel_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF-")


def test_audit_corrupted_csv_files():
    """Audit de la robustesse de l'ingestion face à des fichiers invalides."""
    # 1. Fichier complètement vide
    empty_stream = io.StringIO("")
    with pytest.raises(Exception):
        parse_variant_csv(empty_stream)

    # 2. Fichier avec seulement des virgules
    commas_stream = io.StringIO(",,,,\n,,,,")
    with pytest.raises(DataParsingError):
        parse_variant_csv(commas_stream)

    # 3. Fichier avec du texte non numérique dans la quantité
    text_qty_csv = """code;designation;categorie;quantite;unite
deblai;Déblai;TERRASSEMENT;cinquante_mille;m3
"""
    with pytest.raises(DataParsingError) as exc_info:
        parse_variant_csv(io.StringIO(text_qty_csv))
    assert "invalide" in str(exc_info.value).lower() or "postes valides" in str(exc_info.value).lower()

    # 4. Fichier avec une unité totalement farfelue
    bad_unit_csv = """code;designation;categorie;quantite;unite
deblai;Déblai;TERRASSEMENT;5000;cheval_vapeur
"""
    with pytest.raises(DataParsingError) as exc_info:
        parse_variant_csv(io.StringIO(bad_unit_csv))


def test_audit_extreme_quantities():
    """Audit avec des échelles de grands travaux (dizaines de millions de m3 et centaines de millions d'euros)."""
    meta1 = VariantMetadata(name="Autoroute_A", total_length_m=120000.0, right_of_way_m2=3500000.0)
    meta2 = VariantMetadata(name="Autoroute_B", total_length_m=115000.0, right_of_way_m2=3200000.0)

    v1 = Variant(metadata=meta1)
    v2 = Variant(metadata=meta2)

    # 15 millions de m3 de déblai
    v1.add_item(QuantityItem(code="deblai", designation="Déblais autoroutiers", quantity=15000000.0, unit="m3", category=QuantityCategory.TERRASSEMENT))
    v2.add_item(QuantityItem(code="deblai", designation="Déblais autoroutiers", quantity=12500000.0, unit="m3", category=QuantityCategory.TERRASSEMENT))

    catalog = UnitCostCatalog(currency="EUR")
    catalog.add_price(UnitPrice(code="deblai", designation="Déblai", unit="m3", price=8.50))

    comp = compare_variants(baseline=v1, target=v2, catalog=catalog)

    # 15M * 8.50 = 127 500 000 EUR
    assert comp.baseline_total_cost == 127500000.00
    # 12.5M * 8.50 = 106 250 000 EUR
    assert comp.target_total_cost == 106250000.00
    assert comp.delta_abs_total_cost == -21250000.00

    # Vérification que le formatage ne déborde pas
    excel_bytes = generate_excel_report(comp, v1, v2, catalog)
    pdf_bytes = generate_pdf_report(comp, v1, v2, catalog)
    assert len(excel_bytes) > 0
    assert len(pdf_bytes) > 0


def test_audit_unit_incompatibility_between_variants():
    """Vérifie que des unités incompatibles (m3 vs tonnes) entre deux variantes sont signalées sans calcul absurde."""
    meta1 = VariantMetadata(name="V1", total_length_m=1000.0, right_of_way_m2=10000.0)
    meta2 = VariantMetadata(name="V2", total_length_m=1000.0, right_of_way_m2=10000.0)

    v1 = Variant(metadata=meta1)
    v2 = Variant(metadata=meta2)

    # V1 est mesuré en m3, V2 est mesuré en tonnes pour le même poste
    v1.add_item(QuantityItem(code="grave_bitume", designation="Grave-bitume", quantity=1000.0, unit="m3", category=QuantityCategory.CHAUSSEE))
    v2.add_item(QuantityItem(code="grave_bitume", designation="Grave-bitume", quantity=2400.0, unit="t", category=QuantityCategory.CHAUSSEE))

    comp = compare_variants(baseline=v1, target=v2)

    # Doit avoir détecté l'incompatibilité
    item_gb = comp.items[0]
    assert item_gb.unit_mismatch is True
    assert item_gb.delta_abs_qty is None  # Ne doit pas soustraire 2400 t - 1000 m3 !
    assert item_gb.delta_rel_qty_percent is None
    assert len(comp.unit_mismatches) > 0
    assert "grave_bitume" in comp.unit_mismatches[0]

    # Vérification que l'export gère l'incompatibilité
    excel_bytes = generate_excel_report(comp, v1, v2)
    pdf_bytes = generate_pdf_report(comp, v1, v2)
    assert len(excel_bytes) > 0
    assert len(pdf_bytes) > 0


def test_audit_bpu_unit_incompatibility():
    """Vérifie que l'incompatibilité d'unité entre le BPU et la variante est détectée et n'applique pas un prix erroné."""
    meta = VariantMetadata(name="V1", total_length_m=1000.0, right_of_way_m2=10000.0)
    v = Variant(metadata=meta)
    # Poste en m3
    v.add_item(QuantityItem(code="enrobe", designation="Enrobé", quantity=500.0, unit="m3", category=QuantityCategory.CHAUSSEE))

    # Prix défini en tonnes (t) au lieu de m3
    catalog = UnitCostCatalog(currency="EUR")
    catalog.add_price(UnitPrice(code="enrobe", designation="Enrobé", unit="t", price=75.0))

    cost, cat_costs, missing = calculate_variant_total_cost(v, catalog)

    # Ne doit pas multiplier 500 m3 par 75 €/t sans conversion
    assert cost == 0.0
    assert len(missing) == 1
    assert "incompatible" in missing[0].lower() or "unité bpu" in missing[0].lower()

