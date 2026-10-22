"""Calculation engine for road variant comparisons and cost estimation."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple
from src.core.models import (
    CategoryCostSummary,
    EarthworkBalance,
    EarthworkStatus,
    ItemComparison,
    QuantityCategory,
    QuantityItem,
    UnitCostCatalog,
    Variant,
    VariantComparison,
)


def compute_relative_delta(target: float, baseline: float) -> Optional[float]:
    """Calcule l'écart relatif en pourcentage : ((target - baseline) / baseline) * 100.
    
    Retourne 0.0 si les deux valeurs sont nulles.
    Retourne None si baseline est nulle et target non nulle (division par zéro).
    """
    if math.isclose(baseline, 0.0, abs_tol=1e-9):
        if math.isclose(target, 0.0, abs_tol=1e-9):
            return 0.0
        return None
    return ((target - baseline) / baseline) * 100.0


def is_cut_item(item: QuantityItem) -> bool:
    """Détermine si un poste correspond à du déblai routier."""
    code = item.code.lower()
    designation = item.designation.lower()
    if item.category == QuantityCategory.TERRASSEMENT:
        keywords = ["deblai", "déblai", "cut", "excavation", "roc", "rocher"]
        return any(kw in code or kw in designation for kw in keywords)
    return False


def is_fill_item(item: QuantityItem) -> bool:
    """Détermine si un poste correspond à du remblai routier."""
    code = item.code.lower()
    designation = item.designation.lower()
    if item.category == QuantityCategory.TERRASSEMENT:
        keywords = ["remblai", "fill", "embankment", "corps_de_remblai"]
        return any(kw in code or kw in designation for kw in keywords)
    return False


def calculate_earthwork_balance(
    variant: Variant,
    tolerance_m3: float = 100.0
) -> EarthworkBalance:
    """Calcule le bilan de terrassement (mouvement des terres) d'une variante.
    
    Prend en compte :
    - Volume total en place des déblais (m3)
    - Volume total compacté des remblais (m3)
    - Rendement volumique réutilisable = déblais * (foisonnement * compactage)
    - Solde net = Déblais réutilisables - Remblais
    """
    total_cut_m3 = 0.0
    total_fill_m3 = 0.0

    for item in variant.items.values():
        if is_cut_item(item):
            total_cut_m3 += item.quantity
        elif is_fill_item(item):
            total_fill_m3 += item.quantity

    yield_factor = variant.metadata.swelling_factor * variant.metadata.compaction_factor
    usable_cut_m3 = total_cut_m3 * yield_factor
    net_balance_m3 = usable_cut_m3 - total_fill_m3

    if net_balance_m3 > tolerance_m3:
        status = EarthworkStatus.EXCEDENTAIRE
    elif net_balance_m3 < -tolerance_m3:
        status = EarthworkStatus.DEFICITAIRE
    else:
        status = EarthworkStatus.EQUILIBRE

    return EarthworkBalance(
        cut_total_m3=round(total_cut_m3, 2),
        fill_total_m3=round(total_fill_m3, 2),
        usable_cut_m3=round(usable_cut_m3, 2),
        net_balance_m3=round(net_balance_m3, 2),
        status=status,
    )


def calculate_variant_total_cost(
    variant: Variant,
    catalog: UnitCostCatalog
) -> Tuple[float, Dict[QuantityCategory, float], List[str]]:
    """Calcule le coût total d'une variante et la répartition par famille.
    
    Retourne :
    - Coût total estimé (HT)
    - Dictionnaire des coûts par catégorie
    - Liste des codes d'articles dont le prix unitaire est manquant dans le catalogue
    """
    total_cost = 0.0
    category_costs: Dict[QuantityCategory, float] = {cat: 0.0 for cat in QuantityCategory}
    missing_price_codes: List[str] = []

    for code, item in variant.items.items():
        price_item = catalog.get_price_item(code)
        if price_item is None:
            missing_price_codes.append(code)
            continue
        if price_item.unit != item.unit:
            missing_price_codes.append(f"{code} (unité BPU '{price_item.unit}' ≠ '{item.unit}')")
            continue
        item_cost = item.quantity * price_item.price
        total_cost += item_cost
        category_costs[item.category] += item_cost

    return round(total_cost, 2), category_costs, missing_price_codes


def compare_variants(
    baseline: Variant,
    target: Variant,
    catalog: Optional[UnitCostCatalog] = None
) -> VariantComparison:
    """Compare une variante cible à une variante de référence (baseline).
    
    Calcule :
    - Écarts géométriques (longueur, emprise)
    - Écarts sur chaque poste de quantité (absolu et relatif %)
    - Écarts de terrassements (déblais, remblais, solde)
    - Écarts financiers globaux et par famille de travaux (si un BPU est fourni)
    """
    # 1. Écarts géométriques
    b_len = baseline.metadata.total_length_m
    t_len = target.metadata.total_length_m
    delta_len = t_len - b_len
    delta_len_pct = compute_relative_delta(t_len, b_len)

    b_row = baseline.metadata.right_of_way_m2
    t_row = target.metadata.right_of_way_m2
    delta_row = t_row - b_row
    delta_row_pct = compute_relative_delta(t_row, b_row)

    # 2. Bilan de terrassement
    b_earthwork = calculate_earthwork_balance(baseline)
    t_earthwork = calculate_earthwork_balance(target)
    delta_cut = round(t_earthwork.cut_total_m3 - b_earthwork.cut_total_m3, 2)
    delta_fill = round(t_earthwork.fill_total_m3 - b_earthwork.fill_total_m3, 2)

    # 3. Comparaison détaillée des postes (Union des postes de baseline et target)
    all_codes: Set[str] = set(baseline.items.keys()).union(set(target.items.keys()))
    sorted_codes = sorted(all_codes)

    items_comparison: List[ItemComparison] = []
    category_costs_base: Dict[QuantityCategory, float] = {cat: 0.0 for cat in QuantityCategory}
    category_costs_target: Dict[QuantityCategory, float] = {cat: 0.0 for cat in QuantityCategory}

    baseline_total_cost = 0.0 if catalog else None
    target_total_cost = 0.0 if catalog else None

    unit_mismatches_list: List[str] = []

    for code in sorted_codes:
        b_item = baseline.items.get(code)
        t_item = target.items.get(code)

        # Récupération des attributs descriptifs
        sample_item = t_item if t_item is not None else b_item
        assert sample_item is not None
        designation = sample_item.designation
        category = sample_item.category
        unit = sample_item.unit

        b_qty = b_item.quantity if b_item else 0.0
        t_qty = t_item.quantity if t_item else 0.0

        # Vérification stricte de la cohérence d'unité entre baseline et cible
        unit_mismatch = False
        item_warning = None
        if b_item and t_item and b_item.unit != t_item.unit:
            unit_mismatch = True
            unit = f"{b_item.unit} ≠ {t_item.unit}"
            item_warning = f"Incompatibilité d'unités : {b_item.unit} (Réf) vs {t_item.unit} (Cible)"
            unit_mismatches_list.append(
                f"Poste '{code}' : Unité référence ({b_item.unit}) ≠ Unité cible ({t_item.unit})"
            )
            delta_abs_qty = None
            delta_rel_qty_pct = None
        else:
            delta_abs_qty = round(t_qty - b_qty, 3)
            delta_rel_qty_pct = compute_relative_delta(t_qty, b_qty)
            if delta_rel_qty_pct is not None:
                delta_rel_qty_pct = round(delta_rel_qty_pct, 2)

        # Calcul financier de l'item si catalogue présent
        unit_price = None
        b_cost = None
        t_cost = None
        delta_abs_cost = None
        delta_rel_cost_pct = None

        if catalog:
            price_item = catalog.get_price_item(code)
            if price_item:
                # Vérification que l'unité du BPU concorde avec l'unité du métré
                b_match = (not b_item) or (b_item.unit == price_item.unit)
                t_match = (not t_item) or (t_item.unit == price_item.unit)

                if not b_match or not t_match:
                    unit_mismatches_list.append(
                        f"Poste '{code}' : Unité BPU ({price_item.unit}) incompatible avec le métré."
                    )
                    item_warning = (item_warning or "") + f" Prix BPU en {price_item.unit} incompatible."
                else:
                    unit_price = price_item.price
                    b_cost = round(b_qty * unit_price, 2)
                    t_cost = round(t_qty * unit_price, 2)
                    delta_abs_cost = round(t_cost - b_cost, 2)
                    rel_cost = compute_relative_delta(t_cost, b_cost)
                    delta_rel_cost_pct = round(rel_cost, 2) if rel_cost is not None else None

                    assert baseline_total_cost is not None and target_total_cost is not None
                    baseline_total_cost += b_cost
                    target_total_cost += t_cost
                    category_costs_base[category] += b_cost
                    category_costs_target[category] += t_cost

        items_comparison.append(
            ItemComparison(
                code=code,
                designation=designation,
                category=category,
                unit=unit,
                baseline_qty=b_qty,
                target_qty=t_qty,
                delta_abs_qty=delta_abs_qty,
                delta_rel_qty_percent=delta_rel_qty_pct,
                unit_price=unit_price,
                baseline_cost=b_cost,
                target_cost=t_cost,
                delta_abs_cost=delta_abs_cost,
                delta_rel_cost_percent=delta_rel_cost_pct,
                unit_mismatch=unit_mismatch,
                warning=item_warning,
            )
        )

    # 4. Synthèses financières par catégorie
    category_summaries: List[CategoryCostSummary] = []
    delta_total_cost = None
    delta_rel_total_cost_pct = None

    if catalog is not None and baseline_total_cost is not None and target_total_cost is not None:
        baseline_total_cost = round(baseline_total_cost, 2)
        target_total_cost = round(target_total_cost, 2)
        delta_total_cost = round(target_total_cost - baseline_total_cost, 2)
        rel_tot = compute_relative_delta(target_total_cost, baseline_total_cost)
        delta_rel_total_cost_pct = round(rel_tot, 2) if rel_tot is not None else None

        for cat in QuantityCategory:
            c_base = round(category_costs_base[cat], 2)
            c_target = round(category_costs_target[cat], 2)
            if c_base > 0 or c_target > 0:
                c_delta = round(c_target - c_base, 2)
                rel_c = compute_relative_delta(c_target, c_base)
                c_rel_pct = round(rel_c, 2) if rel_c is not None else None
                category_summaries.append(
                    CategoryCostSummary(
                        category=cat,
                        baseline_cost=c_base,
                        target_cost=c_target,
                        delta_abs_cost=c_delta,
                        delta_rel_cost_percent=c_rel_pct,
                    )
                )

    return VariantComparison(
        baseline_name=baseline.name,
        target_name=target.name,
        items=items_comparison,
        baseline_length_m=round(b_len, 2),
        target_length_m=round(t_len, 2),
        delta_length_m=round(delta_len, 2),
        delta_length_percent=round(delta_len_pct, 2) if delta_len_pct is not None else None,
        baseline_right_of_way_m2=round(b_row, 2),
        target_right_of_way_m2=round(t_row, 2),
        delta_right_of_way_m2=round(delta_row, 2),
        delta_right_of_way_percent=round(delta_row_pct, 2) if delta_row_pct is not None else None,
        baseline_earthwork=b_earthwork,
        target_earthwork=t_earthwork,
        delta_cut_m3=delta_cut,
        delta_fill_m3=delta_fill,
        currency=catalog.currency if catalog else None,
        baseline_total_cost=baseline_total_cost,
        target_total_cost=target_total_cost,
        delta_abs_total_cost=delta_total_cost,
        delta_rel_total_cost_percent=delta_rel_total_cost_pct,
        category_summaries=category_summaries,
        unit_mismatches=unit_mismatches_list,
    )
