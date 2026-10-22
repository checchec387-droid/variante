"""Reusable UI components, tables, and styling for Streamlit."""
from __future__ import annotations

from typing import Dict, List, Optional
import pandas as pd
import streamlit as st

from src.core.calculator import calculate_earthwork_balance
from src.core.models import (
    EarthworkStatus,
    ItemComparison,
    QuantityCategory,
    UnitCostCatalog,
    Variant,
    VariantComparison,
)


def render_header() -> None:
    """Affiche le bandeau d'en-tête professionnel de l'application."""
    st.markdown(
        """
        <div style="background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%); padding: 22px 28px; border-radius: 10px; margin-bottom: 24px; color: white; border-left: 6px solid #0284c7;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h1 style="margin: 0; font-size: 26px; font-weight: 700; color: #f8fafc;">🛣️ Road Variant Comparator</h1>
                    <p style="margin: 6px 0 0 0; font-size: 14px; color: #94a3b8;">
                        Outil d'aide à la décision pour bureaux d'études et ingénieurs VRD | Cubatures, Bilan des terres et Analyse financière
                    </p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_variant_kpi_cards(variant: Variant, catalog: Optional[UnitCostCatalog] = None) -> None:
    """Affiche les métriques clés (KPIs) d'une variante individuelle."""
    earthwork = calculate_earthwork_balance(variant)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="Longueur du tracé",
            value=f"{variant.metadata.total_length_m:,.0f} m",
            help="Longueur totale d'axe en mètres"
        )
    with c2:
        st.metric(
            label="Emprise foncière",
            value=f"{variant.metadata.right_of_way_m2:,.0f} m²",
            help="Superficie nécessaire en mètres carrés"
        )
    with c3:
        st.metric(
            label="Déblais totaux",
            value=f"{earthwork.cut_total_m3:,.0f} m³",
            help="Volume brut des déblais en place"
        )
    with c4:
        st.metric(
            label="Remblais totaux",
            value=f"{earthwork.fill_total_m3:,.0f} m³",
            help="Volume compacté des remblais"
        )

    # Ligne 2 : Solde du mouvement des terres
    status_color = "#16a34a" if earthwork.status == EarthworkStatus.EXCEDENTAIRE else (
        "#dc2626" if earthwork.status == EarthworkStatus.DEFICITAIRE else "#2563eb"
    )
    status_label = "Excédentaire (Mise en dépôt)" if earthwork.status == EarthworkStatus.EXCEDENTAIRE else (
        "Déficitaire (Emprunt extérieur requis)" if earthwork.status == EarthworkStatus.DEFICITAIRE else "Équilibré"
    )

    st.markdown(
        f"""
        <div style="background-color: #f1f5f9; padding: 10px 16px; border-radius: 6px; margin: 10px 0 16px 0; border-left: 4px solid {status_color};">
            <b>Bilan des terres :</b> Solde net de <span style="color: {status_color}; font-weight: bold;">{earthwork.net_balance_m3:+,.0f} m³</span>
            (Déblais réutilisables: {earthwork.usable_cut_m3:,.0f} m³) — <i>Statut : {status_label}</i>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_comparison_dataframe(comparison: VariantComparison) -> pd.DataFrame:
    """Construit un DataFrame formaté pour l'affichage du tableau comparatif poste par poste."""
    rows = []
    for it in comparison.items:
        # Écart relatif formaté
        rel_str = f"{it.delta_rel_qty_percent:+.2f}%" if it.delta_rel_qty_percent is not None else "-"
        
        row_data = {
            "Famille": it.category.value,
            "Code": it.code,
            "Désignation": it.designation,
            "Unité": it.unit,
            f"Réf ({comparison.baseline_name})": f"{it.baseline_qty:,.2f}",
            f"Cible ({comparison.target_name})": f"{it.target_qty:,.2f}",
            "Δ Quantité (Absolu)": f"{it.delta_abs_qty:+,.2f}" if it.delta_abs_qty is not None else ("⚠️ Incompatible" if it.unit_mismatch else "-"),
            "Δ Quantité (%)": rel_str,
        }

        # Données de coût si disponibles
        if comparison.currency and it.unit_price is not None:
            c_rel_str = f"{it.delta_rel_cost_percent:+.2f}%" if it.delta_rel_cost_percent is not None else "-"
            row_data[f"P.U. ({comparison.currency})"] = f"{it.unit_price:,.2f}"
            row_data[f"Coût Réf ({comparison.currency})"] = f"{it.baseline_cost:,.2f}" if it.baseline_cost is not None else "-"
            row_data[f"Coût Cible ({comparison.currency})"] = f"{it.target_cost:,.2f}" if it.target_cost is not None else "-"
            row_data[f"Δ Coût ({comparison.currency})"] = f"{it.delta_abs_cost:+,.2f}" if it.delta_abs_cost is not None else "-"
            row_data["Δ Coût (%)"] = c_rel_str

        rows.append(row_data)

    return pd.DataFrame(rows)


def render_comparison_summary_kpis(comparison: VariantComparison) -> None:
    """Affiche les KPIs comparatifs entre deux variantes."""
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        d_len_pct = f"{comparison.delta_length_percent:+.1f}%" if comparison.delta_length_percent is not None else ""
        st.metric(
            label="Écart de Longueur",
            value=f"{comparison.delta_length_m:+,.0f} m",
            delta=d_len_pct,
            delta_color="inverse",  # Plus court = meilleur
        )
    with c2:
        d_row_pct = f"{comparison.delta_right_of_way_percent:+.1f}%" if comparison.delta_right_of_way_percent is not None else ""
        st.metric(
            label="Écart d'Emprise",
            value=f"{comparison.delta_right_of_way_m2:+,.0f} m²",
            delta=d_row_pct,
            delta_color="inverse",
        )
    with c3:
        st.metric(
            label="Écart Déblais bruts",
            value=f"{comparison.delta_cut_m3:+,.0f} m³",
            help="Différence de déblais en place"
        )
    with c4:
        st.metric(
            label="Écart Remblais",
            value=f"{comparison.delta_fill_m3:+,.0f} m³",
            help="Différence de remblais compactés"
        )

    # Coût global si présent
    if comparison.currency and comparison.delta_abs_total_cost is not None:
        curr = comparison.currency
        st.divider()
        b1, b2, b3 = st.columns(3)
        with b1:
            st.metric(
                label=f"Coût Référence ({comparison.baseline_name})",
                value=f"{comparison.baseline_total_cost:,.2f} {curr}"
            )
        with b2:
            st.metric(
                label=f"Coût Cible ({comparison.target_name})",
                value=f"{comparison.target_total_cost:,.2f} {curr}"
            )
        with b3:
            d_pct_str = f"{comparison.delta_rel_total_cost_percent:+.2f}%" if comparison.delta_rel_total_cost_percent is not None else ""
            st.metric(
                label="Écart Financier Total",
                value=f"{comparison.delta_abs_total_cost:+,.2f} {curr}",
                delta=d_pct_str,
                delta_color="inverse",  # Économie = vert
            )
