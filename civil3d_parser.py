"""Parser for Civil 3D volume report tables (Section by section / Profile volumes)."""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd

from src.core.models import (
    QuantityCategory,
    QuantityItem,
    Variant,
    VariantMetadata,
)
from src.io.validators import ValidationReport


def parse_station_to_meters(station_val: Any) -> float:
    """Convertit une station Civil 3D en mètres (ex: '1+250.50' -> 1250.50, '1250.50' -> 1250.50)."""
    if pd.isna(station_val):
        return 0.0
    s_str = str(station_val).strip()
    # Format standard Civil 3D : X+YYY.ZZ
    if "+" in s_str:
        parts = s_str.split("+")
        try:
            km_part = float(parts[0])
            m_part = float(parts[1])
            return (km_part * 1000.0) + m_part
        except (ValueError, IndexError):
            pass
    # Format numérique direct
    try:
        return float(s_str.replace(" ", "").replace(",", "."))
    except ValueError:
        return 0.0


def parse_civil3d_volume_report(
    file_path_or_bytes: Union[str, Path, io.BytesIO, io.StringIO],
    variant_name: str = "Variante Civil 3D",
    file_type: str = "csv",
    right_of_way_m2: float = 0.0
) -> Tuple[Variant, ValidationReport]:
    """Parse un rapport de volume/cubature exporté depuis Autodesk Civil 3D.
    
    Détecte automatiquement :
    - Les stations (PKs)
    - Les volumes incrémentaux ou cumulés de déblais (Cut) et remblais (Fill)
    - Calcule la longueur totale du tronçon = PK_max - PK_min
    - Génère les postes de terrassements correspondants
    """
    report = ValidationReport()

    if file_type.lower() in ["excel", "xlsx", "xls"]:
        df = pd.read_excel(file_path_or_bytes)
    else:
        try:
            df = pd.read_csv(file_path_or_bytes, sep=None, engine="python")
        except Exception:
            if isinstance(file_path_or_bytes, (io.BytesIO, io.StringIO)):
                file_path_or_bytes.seek(0)
            df = pd.read_csv(file_path_or_bytes, sep=";")

    # Recherche des colonnes par mots-clés et types (Surface vs Volume)
    col_mapping: Dict[str, str] = {}
    for col in df.columns:
        c_low = str(col).strip().lower()
        is_area = any(k in c_low for k in ["area", "surf", "section", "sq.m", "m2", "m²"])
        is_cumul = any(k in c_low for k in ["cumul", "cum.", "cum ", "accum", "total"])

        if any(k in c_low for k in ["station", "pk", "profil", "chainage"]):
            col_mapping["station"] = col
        elif not is_area and any(k in c_low for k in ["cut", "deblai"]):
            if is_cumul:
                col_mapping["cumul_cut"] = col
            elif any(k in c_low for k in ["vol", "cu.m", "m3"]):
                col_mapping.setdefault("inc_cut", col)
            else:
                col_mapping.setdefault("inc_cut", col)
        elif not is_area and any(k in c_low for k in ["fill", "remblai"]):
            if is_cumul:
                col_mapping["cumul_fill"] = col
            elif any(k in c_low for k in ["vol", "cu.m", "m3"]):
                col_mapping.setdefault("inc_fill", col)
            else:
                col_mapping.setdefault("inc_fill", col)

    # Validation de la présence des colonnes indispensables
    has_cut = "cumul_cut" in col_mapping or "inc_cut" in col_mapping
    has_fill = "cumul_fill" in col_mapping or "inc_fill" in col_mapping

    if not has_cut and not has_fill:
        report.add_error("Impossible d'identifier les colonnes de déblai (Cut) ou remblai (Fill) de Civil 3D.")
        raise ValueError("Colonnes Civil 3D non reconnues")

    # Calcul des totaux de terrassement
    total_cut_m3 = 0.0
    if "cumul_cut" in col_mapping:
        total_cut_m3 = float(pd.to_numeric(df[col_mapping["cumul_cut"]], errors="coerce").dropna().iloc[-1])
    elif "inc_cut" in col_mapping:
        total_cut_m3 = float(pd.to_numeric(df[col_mapping["inc_cut"]], errors="coerce").dropna().sum())

    total_fill_m3 = 0.0
    if "cumul_fill" in col_mapping:
        total_fill_m3 = float(pd.to_numeric(df[col_mapping["cumul_fill"]], errors="coerce").dropna().iloc[-1])
    elif "inc_fill" in col_mapping:
        total_fill_m3 = float(pd.to_numeric(df[col_mapping["inc_fill"]], errors="coerce").dropna().sum())

    # Calcul de la longueur à partir des stations
    total_length_m = 0.0
    if "station" in col_mapping:
        stations_m = df[col_mapping["station"]].apply(parse_station_to_meters)
        valid_stations = stations_m.dropna()
        if len(valid_stations) >= 2:
            total_length_m = abs(float(valid_stations.max() - valid_stations.min()))

    meta = VariantMetadata(
        name=variant_name,
        total_length_m=round(total_length_m, 2),
        right_of_way_m2=right_of_way_m2,
        swelling_factor=1.20,
        compaction_factor=0.90,
    )
    variant = Variant(metadata=meta)

    # Ajout des postes de terrassements extraits
    variant.add_item(
        QuantityItem(
            code="deblai_civil3d",
            designation="Déblais bruts (Export Civil 3D)",
            category=QuantityCategory.TERRASSEMENT,
            quantity=round(max(0.0, total_cut_m3), 2),
            unit="m3",
        )
    )
    variant.add_item(
        QuantityItem(
            code="remblai_civil3d",
            designation="Remblais bruts (Export Civil 3D)",
            category=QuantityCategory.TERRASSEMENT,
            quantity=round(max(0.0, total_fill_m3), 2),
            unit="m3",
        )
    )

    return variant, report
