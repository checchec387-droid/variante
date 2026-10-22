"""Unit tests for the calculation engine with independently calculated expected results."""
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


def test_compute_relative_delta():
    """Vérification des calculs de pourcentage d'écart et cas limites mathématiques."""
    # Cas normal positif: passage de 100 à 150 (+50%)
    assert compute_relative_delta(150.0, 100.0) == 50.0

    # Cas normal négatif: passage de 200 à 150 (-25%)
    assert compute_relative_delta(150.0, 200.0) == -25.0

    # Aucun changement
    assert compute_relative_delta(50.0, 50.0) == 0.0

    # Les deux sont nuls
    assert compute_relative_delta(0.0, 0.0) == 0.0

    # Division par zéro (baseline = 0, nouveau poste apparu)
    assert compute_relative_delta(100.0, 0.0) is None


def test_earthwork_balance_variant_a(variant_a_fixture: Variant):
    """Vérifie le bilan de terrassement de la Variante A (excédentaire attendu).
    
    Déblai total attendu : 40 000 (meuble) + 10 000 (rocher) = 50 000 m3
    Rendement foisonnement*compactage attendu : 1.20 * 0.90 = 1.08
    Déblais réutilisables attendus : 50 000 * 1.08 = 54 000 m3
    Remblai total attendu : 45 000 m3
    Solde net attendu : 54 000 - 45 000 = +9 000 m3 (EXCEDENTAIRE)
    """
    balance = calculate_earthwork_balance(variant_a_fixture)

    assert balance.cut_total_m3 == 50000.0
    assert balance.fill_total_m3 == 45000.0
    assert balance.usable_cut_m3 == 54000.0
    assert balance.net_balance_m3 == 9000.0
    assert balance.status == EarthworkStatus.EXCEDENTAIRE


def test_earthwork_balance_variant_b(variant_b_fixture: Variant):
    """Vérifie le bilan de terrassement de la Variante B (déficitaire attendu).
    
    Déblai total : 30 000 + 15 000 = 45 000 m3
    Déblais réutilisables : 45 000 * 1.08 = 48 600 m3
    Remblai total : 52 000 m3
    Solde net : 48 600 - 52 000 = -3 400 m3 (DEFICITAIRE)
    """
    balance = calculate_earthwork_balance(variant_b_fixture)

    assert balance.cut_total_m3 == 45000.0
    assert balance.fill_total_m3 == 52000.0
    assert balance.usable_cut_m3 == 48600.0
    assert balance.net_balance_m3 == -3400.0
    assert balance.status == EarthworkStatus.DEFICITAIRE


def test_variant_cost_calculation(variant_a_fixture: Variant, catalog_fixture: UnitCostCatalog):
    """Vérifie le calcul des coûts par poste et globaux de la Variante A.
    
    Détail attendu calculé indépendamment :
    - Déblai meuble : 40 000 * 6.50 = 260 000 EUR
    - Déblai rocher  : 10 000 * 18.00 = 180 000 EUR
    - Remblai        : 45 000 * 8.00 = 360 000 EUR
    Sous-total Terrassement = 800 000.00 EUR
    
    - Béton bitumineux : 25 000 * 15.00 = 375 000 EUR
    - Grave GNT        : 15 000 * 28.00 = 420 000 EUR
    Sous-total Chaussée = 795 000.00 EUR
    
    - Fossés bétonnés  : 3 500 * 45.00 = 157 500.00 EUR (Assainissement)
    - Glissières métal : 2 000 * 60.00 = 120 000.00 EUR (Équipement)
    
    Total général attendu = 1 872 500.00 EUR
    """
    total_cost, category_costs, missing = calculate_variant_total_cost(variant_a_fixture, catalog_fixture)

    assert missing == []
    assert total_cost == 1872500.00
    assert category_costs[QuantityCategory.TERRASSEMENT] == 800000.00
    assert category_costs[QuantityCategory.CHAUSSEE] == 795000.00
    assert category_costs[QuantityCategory.ASSAINISSEMENT] == 157500.00
    assert category_costs[QuantityCategory.EQUIPEMENT] == 120000.00


def test_variant_cost_calculation_variant_b(variant_b_fixture: Variant, catalog_fixture: UnitCostCatalog):
    """Vérifie le coût total de la Variante B.
    
    - Déblai meuble: 30 000 * 6.50 = 195 000
    - Déblai rocher: 15 000 * 18.00 = 270 000
    - Remblai: 52 000 * 8.00 = 416 000
    Sous-total Terrassement = 881 000 EUR
    
    - BB: 22 000 * 15.00 = 330 000
    - GNT: 13 200 * 28.00 = 369 600
    Sous-total Chaussée = 699 600 EUR
    
    - Fossés: 3 000 * 45.00 = 135 000 EUR
    - Glissières: 2 500 * 60.00 = 150 000 EUR
    
    Total attendu = 1 865 600.00 EUR
    """
    total_cost, category_costs, missing = calculate_variant_total_cost(variant_b_fixture, catalog_fixture)

    assert missing == []
    assert total_cost == 1865600.00
    assert category_costs[QuantityCategory.TERRASSEMENT] == 881000.00
    assert category_costs[QuantityCategory.CHAUSSEE] == 699600.00


def test_variant_cost_with_missing_prices(variant_a_fixture: Variant):
    """Vérifie que les postes sans prix dans le catalogue sont bien identifiés dans la liste 'missing'."""
    incomplete_catalog = UnitCostCatalog(currency="EUR")
    # On n'ajoute qu'un seul prix
    incomplete_catalog.add_price(
        UnitPrice(code="deblai_meuble", designation="Déblai meuble", unit="m3", price=6.50)
    )

    total_cost, category_costs, missing = calculate_variant_total_cost(variant_a_fixture, incomplete_catalog)

    # Déblai meuble (40 000 * 6.50 = 260 000)
    assert total_cost == 260000.00
    # Les 6 autres codes doivent être dans missing
    assert len(missing) == 6
    assert "deblai_rocher" in missing
    assert "remblai" in missing
    assert "couche_roulement_bb" in missing


def test_compare_variants_deltas(
    variant_a_fixture: Variant,
    variant_b_fixture: Variant,
    catalog_fixture: UnitCostCatalog
):
    """Vérifie la comparaison complète entre Variante A (Baseline) et Variante B (Target)."""
    comparison = compare_variants(
        baseline=variant_a_fixture,
        target=variant_b_fixture,
        catalog=catalog_fixture
    )

    # 1. Écarts géométriques
    # Longueur : 2200 - 2500 = -300 m, soit (-300 / 2500) * 100 = -12.0%
    assert comparison.delta_length_m == -300.0
    assert comparison.delta_length_percent == -12.0

    # Emprise : 46000 - 50000 = -4000 m2, soit (-4000 / 50000) * 100 = -8.0%
    assert comparison.delta_right_of_way_m2 == -4000.0
    assert comparison.delta_right_of_way_percent == -8.0

    # 2. Terrassements
    # Déblais : 45 000 - 50 000 = -5 000 m3
    assert comparison.delta_cut_m3 == -5000.0
    # Remblais : 52 000 - 45 000 = +7 000 m3
    assert comparison.delta_fill_m3 == 7000.0

    # 3. Écart financier total
    # Total A = 1 872 500 EUR, Total B = 1 865 600 EUR
    # Delta absolu = 1 865 600 - 1 872 500 = -6 900.00 EUR
    # Delta relatif = (-6900 / 1872500) * 100 = -0.36849... -> arrondi -0.37%
    assert comparison.baseline_total_cost == 1872500.00
    assert comparison.target_total_cost == 1865600.00
    assert comparison.delta_abs_total_cost == -6900.00
    assert comparison.delta_rel_total_cost_percent == pytest.approx(-0.37, abs=0.01)

    # 4. Vérification d'un poste élémentaire : deblai_meuble
    items_by_code = {it.code: it for it in comparison.items}
    item_dm = items_by_code["deblai_meuble"]
    assert item_dm.baseline_qty == 40000.0
    assert item_dm.target_qty == 30000.0
    assert item_dm.delta_abs_qty == -10000.0
    assert item_dm.delta_rel_qty_percent == -25.0
    assert item_dm.unit_price == 6.50
    assert item_dm.delta_abs_cost == -65000.00
    assert item_dm.delta_rel_cost_percent == -25.0


def test_comparison_with_disjoint_items():
    """Vérifie le comportement lorsqu'un poste existe dans une variante mais pas dans l'autre."""
    meta1 = VariantMetadata(name="V1", total_length_m=1000, right_of_way_m2=10000)
    meta2 = VariantMetadata(name="V2", total_length_m=1000, right_of_way_m2=10000)

    v1 = Variant(metadata=meta1)
    v1.add_item(QuantityItem(code="item_a", designation="Item A", quantity=100.0, unit="m"))

    v2 = Variant(metadata=meta2)
    v2.add_item(QuantityItem(code="item_b", designation="Item B", quantity=50.0, unit="m"))

    comparison = compare_variants(baseline=v1, target=v2)
    items_by_code = {it.code: it for it in comparison.items}

    # Item A : présent dans base (100), absent dans target (0)
    # Delta = 0 - 100 = -100 (-100%)
    item_a = items_by_code["item_a"]
    assert item_a.baseline_qty == 100.0
    assert item_a.target_qty == 0.0
    assert item_a.delta_abs_qty == -100.0
    assert item_a.delta_rel_qty_percent == -100.0

    # Item B : absent dans base (0), présent dans target (50)
    # Delta = 50 - 0 = +50, pourcentage = None (évite division par zéro)
    item_b = items_by_code["item_b"]
    assert item_b.baseline_qty == 0.0
    assert item_b.target_qty == 50.0
    assert item_b.delta_abs_qty == 50.0
    assert item_b.delta_rel_qty_percent is None
