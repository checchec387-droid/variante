"""State management for the Streamlit application."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import streamlit as st

from src.core.models import UnitCostCatalog, Variant
from src.io.parsers import parse_cost_catalog, parse_variant_csv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"


def init_session_state() -> None:
    """Initialise les variables d'état centralisées de la session Streamlit."""
    if "variants" not in st.session_state:
        st.session_state.variants = {}  # Dict[str, Variant]
    if "catalog" not in st.session_state:
        st.session_state.catalog = None  # Optional[UnitCostCatalog]
    if "baseline_name" not in st.session_state:
        st.session_state.baseline_name = None
    if "activity_logs" not in st.session_state:
        st.session_state.activity_logs = []


def add_log(message: str) -> None:
    """Ajoute une entrée dans le journal d'activité de la session."""
    if "activity_logs" not in st.session_state:
        st.session_state.activity_logs = []
    st.session_state.activity_logs.insert(0, message)


def add_variant_to_state(variant: Variant) -> None:
    """Enregistre ou met à jour une variante dans la session."""
    init_session_state()
    st.session_state.variants[variant.name] = variant
    # Si aucune baseline n'est définie, la première variante importée devient la baseline par défaut
    if st.session_state.baseline_name is None or st.session_state.baseline_name not in st.session_state.variants:
        st.session_state.baseline_name = variant.name
    add_log(f"Variante '{variant.name}' ajoutée ({len(variant.items)} postes).")


def remove_variant_from_state(name: str) -> None:
    """Supprime une variante de la session."""
    init_session_state()
    if name in st.session_state.variants:
        del st.session_state.variants[name]
        add_log(f"Variante '{name}' supprimée.")
        # Réassignation de la baseline si celle-ci a été supprimée
        if st.session_state.baseline_name == name:
            remaining = list(st.session_state.variants.keys())
            st.session_state.baseline_name = remaining[0] if remaining else None


def set_catalog_in_state(catalog: UnitCostCatalog) -> None:
    """Enregistre le bordereau des prix unitaires dans la session."""
    init_session_state()
    st.session_state.catalog = catalog
    add_log(f"BPU mis à jour ({len(catalog.prices)} prix en {catalog.currency}).")


def load_demo_dataset() -> bool:
    """Charge en un clic le jeu de données d'exemple certifié (Variante A, B et BPU)."""
    init_session_state()
    try:
        var_a_file = SAMPLES_DIR / "variante_A_reference.csv"
        var_b_file = SAMPLES_DIR / "variante_B_alternative.csv"
        bpu_file = SAMPLES_DIR / "bpu_prix_reference.csv"

        if not (var_a_file.exists() and var_b_file.exists() and bpu_file.exists()):
            return False

        # Chargement Variante A
        var_a, rep_a = parse_variant_csv(var_a_file, default_name="Variante A (Référence)")
        var_a.metadata.total_length_m = 2500.0
        var_a.metadata.right_of_way_m2 = 50000.0
        st.session_state.variants[var_a.name] = var_a

        # Chargement Variante B
        var_b, rep_b = parse_variant_csv(var_b_file, default_name="Variante B (Alternative)")
        var_b.metadata.total_length_m = 2200.0
        var_b.metadata.right_of_way_m2 = 46000.0
        st.session_state.variants[var_b.name] = var_b

        # Chargement BPU
        catalog, rep_c = parse_cost_catalog(bpu_file, file_type="csv", currency="EUR")
        st.session_state.catalog = catalog

        st.session_state.baseline_name = var_a.name
        add_log("Jeu de démonstration chargé avec succès (Variante A, Variante B et BPU).")
        return True
    except Exception as e:
        add_log(f"Erreur lors du chargement de la démo: {e}")
        return False


def clear_all_data() -> None:
    """Réinitialise toutes les données en session."""
    st.session_state.variants = {}
    st.session_state.catalog = None
    st.session_state.baseline_name = None
    add_log("Toutes les données ont été réinitialisées.")
