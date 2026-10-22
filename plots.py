"""Plotly visualization charts for Road Variant Comparator."""
from __future__ import annotations

from typing import List, Optional
import plotly.graph_objects as go
import plotly.express as px

from src.core.calculator import calculate_earthwork_balance
from src.core.models import (
    EarthworkBalance,
    EarthworkStatus,
    QuantityCategory,
    Variant,
    VariantComparison,
)


def plot_earthwork_comparison(variants: List[Variant]) -> go.Figure:
    """Graphique comparatif des mouvements des terres (Déblais, Remblais, Réutilisables, Solde net)."""
    var_names = [v.name for v in variants]
    balances: List[EarthworkBalance] = [calculate_earthwork_balance(v) for v in variants]

    cuts = [b.cut_total_m3 for b in balances]
    usable_cuts = [b.usable_cut_m3 for b in balances]
    fills = [b.fill_total_m3 for b in balances]
    nets = [b.net_balance_m3 for b in balances]

    fig = go.Figure()

    # Déblais bruts
    fig.add_trace(go.Bar(
        x=var_names,
        y=cuts,
        name="Déblais bruts en place (m³)",
        marker_color="#b45309",
        text=[f"{v:,.0f} m³" for v in cuts],
        textposition="auto",
    ))

    # Déblais réutilisables (foisonnés et compactés)
    fig.add_trace(go.Bar(
        x=var_names,
        y=usable_cuts,
        name="Déblais réutilisables (m³)",
        marker_color="#f59e0b",
        text=[f"{v:,.0f} m³" for v in usable_cuts],
        textposition="auto",
    ))

    # Remblais
    fig.add_trace(go.Bar(
        x=var_names,
        y=fills,
        name="Remblais compactés (m³)",
        marker_color="#2563eb",
        text=[f"{v:,.0f} m³" for v in fills],
        textposition="auto",
    ))

    # Solde net (Excédent / Déficit)
    net_colors = ["#16a34a" if n >= 0 else "#dc2626" for n in nets]
    fig.add_trace(go.Bar(
        x=var_names,
        y=nets,
        name="Solde net (Excédent + / Déficit -)",
        marker_color=net_colors,
        text=[f"{n:+,.0f} m³" for n in nets],
        textposition="outside",
    ))

    fig.update_layout(
        title="<b>Bilan et Équilibre des Terrassements par Variante</b>",
        barmode="group",
        xaxis_title="Variantes",
        yaxis_title="Volume (m³)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=480,
        margin=dict(l=40, r=40, t=80, b=40),
    )
    return fig


def plot_total_costs_bar(
    comparisons: List[VariantComparison],
    baseline_name: str,
    baseline_cost: float,
    currency: str = "EUR"
) -> go.Figure:
    """Graphique en barres des coûts globaux avec repère de la variante de référence."""
    names = [baseline_name] + [c.target_name for c in comparisons]
    costs = [baseline_cost] + [c.target_total_cost or 0.0 for c in comparisons]
    
    # Couleurs : gris foncé pour baseline, vert si économie, rouge si surcoût
    colors = ["#475569"]
    for c in comparisons:
        delta = c.delta_abs_total_cost or 0.0
        if delta < 0:
            colors.append("#16a34a")  # Économie
        elif delta > 0:
            colors.append("#dc2626")  # Surcoût
        else:
            colors.append("#64748b")

    text_labels = []
    for idx, (name, cost) in enumerate(zip(names, costs)):
        if idx == 0:
            text_labels.append(f"{cost:,.0f} {currency}<br><b>(Référence)</b>")
        else:
            comp = comparisons[idx - 1]
            d_abs = comp.delta_abs_total_cost or 0.0
            d_pct = comp.delta_rel_total_cost_percent
            pct_str = f" ({d_pct:+.2f}%)" if d_pct is not None else ""
            text_labels.append(f"{cost:,.0f} {currency}<br>Δ {d_abs:+,.0f}{pct_str}")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=names,
        y=costs,
        marker_color=colors,
        text=text_labels,
        textposition="outside",
    ))

    fig.update_layout(
        title=f"<b>Comparaison des Coûts Globaux Estimés ({currency})</b>",
        xaxis_title="Variantes",
        yaxis_title=f"Montant Total HT ({currency})",
        template="plotly_white",
        height=460,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def plot_cost_breakdown_by_category(
    comparison: VariantComparison,
    currency: str = "EUR"
) -> go.Figure:
    """Graphique comparatif des coûts répartis par grande famille de travaux."""
    if not comparison.category_summaries:
        return go.Figure()

    cats = [cs.category.value for cs in comparison.category_summaries]
    base_costs = [cs.baseline_cost for cs in comparison.category_summaries]
    target_costs = [cs.target_cost for cs in comparison.category_summaries]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=f"Réf: {comparison.baseline_name}",
        x=cats,
        y=base_costs,
        marker_color="#64748b",
        text=[f"{v:,.0f} {currency}" for v in base_costs],
        textposition="auto",
    ))
    fig.add_trace(go.Bar(
        name=f"Cible: {comparison.target_name}",
        x=cats,
        y=target_costs,
        marker_color="#0284c7",
        text=[f"{v:,.0f} {currency}" for v in target_costs],
        textposition="auto",
    ))

    fig.update_layout(
        title=f"<b>Répartition des Coûts par Famille de Travaux ({currency})</b>",
        barmode="group",
        xaxis_title="Lots / Familles de travaux",
        yaxis_title=f"Montant HT ({currency})",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
        margin=dict(l=40, r=40, t=70, b=40),
    )
    return fig


def plot_deltas_tornado(
    comparison: VariantComparison,
    top_n: int = 10
) -> go.Figure:
    """Graphique Tornado des principaux écarts relatifs (%) entre les variantes."""
    valid_items = [
        it for it in comparison.items
        if it.delta_rel_qty_percent is not None and abs(it.delta_abs_qty) > 0.001
    ]
    # Trier par amplitude absolue de l'écart
    sorted_items = sorted(valid_items, key=lambda x: abs(x.delta_rel_qty_percent or 0.0), reverse=True)[:top_n]
    if not sorted_items:
        return go.Figure()

    # Inverser pour avoir le plus grand en haut
    sorted_items = sorted_items[::-1]

    labels = [it.designation[:35] for it in sorted_items]
    pcts = [it.delta_rel_qty_percent or 0.0 for it in sorted_items]
    colors = ["#dc2626" if p > 0 else "#16a34a" for p in pcts]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels,
        x=pcts,
        orientation="h",
        marker_color=colors,
        text=[f"{p:+.1f}%" for p in pcts],
        textposition="outside",
    ))

    fig.update_layout(
        title=f"<b>Écarts Relatifs de Quantités (%) : {comparison.target_name} vs {comparison.baseline_name}</b>",
        xaxis_title="Écart relatif (%) [Vert: Réduction de volume / Rouge: Augmentation]",
        yaxis_title="Postes de travaux",
        template="plotly_white",
        height=max(380, len(labels) * 35),
        margin=dict(l=10, r=40, t=60, b=40),
    )
    return fig
