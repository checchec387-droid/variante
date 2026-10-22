"""Pytest fixtures and test reference data for Road Variant Comparator."""
import pytest
from src.core.models import (
    QuantityCategory,
    QuantityItem,
    UnitCostCatalog,
    UnitPrice,
    Variant,
    VariantMetadata,
)


@pytest.fixture
def catalog_fixture() -> UnitCostCatalog:
    """Catalogue de prix unitaires de référence pour les tests."""
    catalog = UnitCostCatalog(currency="EUR")
    prices = [
        UnitPrice(code="deblai_meuble", designation="Déblai meuble", unit="m3", price=6.50, category=QuantityCategory.TERRASSEMENT),
        UnitPrice(code="deblai_rocher", designation="Déblai rocheux", unit="m3", price=18.00, category=QuantityCategory.TERRASSEMENT),
        UnitPrice(code="remblai", designation="Remblai compacté", unit="m3", price=8.00, category=QuantityCategory.TERRASSEMENT),
        UnitPrice(code="couche_roulement_bb", designation="Béton bitumineux (roulement)", unit="m2", price=15.00, category=QuantityCategory.CHAUSSEE),
        UnitPrice(code="couche_base_gnt", designation="Grave non traitée (base)", unit="m3", price=28.00, category=QuantityCategory.CHAUSSEE),
        UnitPrice(code="assainissement_fosses", designation="Fossés bétonnés trapézoïdaux", unit="ml", price=45.00, category=QuantityCategory.ASSAINISSEMENT),
        UnitPrice(code="glissiere_securite", designation="Glissières métalliques", unit="ml", price=60.00, category=QuantityCategory.EQUIPEMENT),
    ]
    for p in prices:
        catalog.add_price(p)
    return catalog


@pytest.fixture
def variant_a_fixture() -> Variant:
    """Variante A (Baseline de référence pour les tests).
    
    Longueur: 2500 m, Emprise: 50 000 m2
    Déblai meuble: 40 000 m3
    Déblai rocher: 10 000 m3
    Remblai: 45 000 m3
    BB: 25 000 m2
    GNT: 15 000 m3
    Fossés: 3 500 ml
    Glissières: 2 000 ml
    """
    meta = VariantMetadata(
        name="Variante A (Référence)",
        code="VAR-A",
        total_length_m=2500.0,
        right_of_row_m2=50000.0,
        right_of_way_m2=50000.0,
        swelling_factor=1.20,
        compaction_factor=0.90,
    )
    var = Variant(metadata=meta)
    items = [
        QuantityItem(code="deblai_meuble", designation="Déblai meuble", category=QuantityCategory.TERRASSEMENT, quantity=40000.0, unit="m3"),
        QuantityItem(code="deblai_rocher", designation="Déblai rocheux", category=QuantityCategory.TERRASSEMENT, quantity=10000.0, unit="m3"),
        QuantityItem(code="remblai", designation="Remblai compacté", category=QuantityCategory.TERRASSEMENT, quantity=45000.0, unit="m3"),
        QuantityItem(code="couche_roulement_bb", designation="Béton bitumineux", category=QuantityCategory.CHAUSSEE, quantity=25000.0, unit="m2"),
        QuantityItem(code="couche_base_gnt", designation="Grave non traitée", category=QuantityCategory.CHAUSSEE, quantity=15000.0, unit="m3"),
        QuantityItem(code="assainissement_fosses", designation="Fossés", category=QuantityCategory.ASSAINISSEMENT, quantity=3500.0, unit="ml"),
        QuantityItem(code="glissiere_securite", designation="Glissières", category=QuantityCategory.EQUIPEMENT, quantity=2000.0, unit="ml"),
    ]
    for it in items:
        var.add_item(it)
    return var


@pytest.fixture
def variant_b_fixture() -> Variant:
    """Variante B (Variante cible optimisée pour les tests).
    
    Longueur: 2200 m, Emprise: 46 000 m2
    Déblai meuble: 30 000 m3
    Déblai rocher: 15 000 m3
    Remblai: 52 000 m3
    BB: 22 000 m2
    GNT: 13 200 m3
    Fossés: 3 000 ml
    Glissières: 2 500 ml
    """
    meta = VariantMetadata(
        name="Variante B (Alternative)",
        code="VAR-B",
        total_length_m=2200.0,
        right_of_way_m2=46000.0,
        swelling_factor=1.20,
        compaction_factor=0.90,
    )
    var = Variant(metadata=meta)
    items = [
        QuantityItem(code="deblai_meuble", designation="Déblai meuble", category=QuantityCategory.TERRASSEMENT, quantity=30000.0, unit="m3"),
        QuantityItem(code="deblai_rocher", designation="Déblai rocheux", category=QuantityCategory.TERRASSEMENT, quantity=15000.0, unit="m3"),
        QuantityItem(code="remblai", designation="Remblai compacté", category=QuantityCategory.TERRASSEMENT, quantity=52000.0, unit="m3"),
        QuantityItem(code="couche_roulement_bb", designation="Béton bitumineux", category=QuantityCategory.CHAUSSEE, quantity=22000.0, unit="m2"),
        QuantityItem(code="couche_base_gnt", designation="Grave non traitée", category=QuantityCategory.CHAUSSEE, quantity=13200.0, unit="m3"),
        QuantityItem(code="assainissement_fosses", designation="Fossés", category=QuantityCategory.ASSAINISSEMENT, quantity=3000.0, unit="ml"),
        QuantityItem(code="glissiere_securite", designation="Glissières", category=QuantityCategory.EQUIPEMENT, quantity=2500.0, unit="ml"),
    ]
    for it in items:
        var.add_item(it)
    return var
