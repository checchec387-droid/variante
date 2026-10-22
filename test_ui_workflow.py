"""End-to-end integration tests for UI components, plots, and state management."""
import pytest
from src.core.calculator import compare_variants
from src.ui.components import format_comparison_dataframe
from src.ui.plots import (
    plot_cost_breakdown_by_category,
    plot_deltas_tornado,
    plot_earthwork_comparison,
    plot_total_costs_bar,
)
from src.ui.state import (
    add_variant_to_state,
    clear_all_data,
    init_session_state,
    load_demo_dataset,
    remove_variant_from_state,
)


def test_ui_state_and_demo_loader():
    """Vérifie le cycle de vie de l'état de session et le chargement des données de démonstration."""
    # Simulation de session Streamlit
    import streamlit as st

    clear_all_data()
    assert len(st.session_state.variants) == 0
    assert st.session_state.catalog is None

    # Chargement démo
    success = load_demo_dataset()
    assert success is True
    assert len(st.session_state.variants) == 2
    assert "Variante A (Référence)" in st.session_state.variants
    assert "Variante B (Alternative)" in st.session_state.variants
    assert st.session_state.catalog is not None
    assert st.session_state.baseline_name == "Variante A (Référence)"

    # Suppression d'une variante
    remove_variant_from_state("Variante B (Alternative)")
    assert len(st.session_state.variants) == 1
    assert "Variante B (Alternative)" not in st.session_state.variants

    # Nettoyage
    clear_all_data()
    assert len(st.session_state.variants) == 0


def test_ui_plots_generation(variant_a_fixture, variant_b_fixture, catalog_fixture):
    """Vérifie que tous les générateurs de graphiques Plotly produisent des figures valides."""
    # 1. Graphique terrassements
    fig_earthwork = plot_earthwork_comparison([variant_a_fixture, variant_b_fixture])
    assert fig_earthwork is not None
    assert len(fig_earthwork.data) == 4  # Déblais, Déblais réutilisables, Remblais, Solde

    # Comparaison
    comp = compare_variants(
        baseline=variant_a_fixture,
        target=variant_b_fixture,
        catalog=catalog_fixture
    )

    # 2. Graphique coûts globaux
    fig_costs = plot_total_costs_bar(
        comparisons=[comp],
        baseline_name=variant_a_fixture.name,
        baseline_cost=1872500.0,
        currency="EUR"
    )
    assert fig_costs is not None
    assert len(fig_costs.data) == 1

    # 3. Répartition par catégorie
    fig_cat = plot_cost_breakdown_by_category(comp, currency="EUR")
    assert fig_cat is not None
    assert len(fig_cat.data) == 2  # Référence et Cible

    # 4. Tornado
    fig_tornado = plot_deltas_tornado(comp)
    assert fig_tornado is not None
    assert len(fig_tornado.data) == 1


def test_ui_comparison_dataframe_formatting(variant_a_fixture, variant_b_fixture, catalog_fixture):
    """Vérifie la mise en forme du tableau comparatif pour Streamlit."""
    comp = compare_variants(
        baseline=variant_a_fixture,
        target=variant_b_fixture,
        catalog=catalog_fixture
    )
    df = format_comparison_dataframe(comp)

    assert not df.empty
    assert "Code" in df.columns
    assert "Famille" in df.columns
    assert "Δ Quantité (Absolu)" in df.columns
    assert "Δ Quantité (%)" in df.columns
    assert "Δ Coût (EUR)" in df.columns

    # Vérification d'une valeur formatée
    row_dm = df[df["Code"] == "deblai_meuble"].iloc[0]
    assert row_dm["Δ Quantité (%)"] == "-25.00%"
    assert row_dm["Δ Coût (%)"] == "-25.00%"
