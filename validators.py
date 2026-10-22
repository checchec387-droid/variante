"""Validation logic for road variant data, units, and integrity."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from src.core.models import (
    UNIT_ALIASES,
    CanonicalUnit,
    QuantityCategory,
    QuantityItem,
    Variant,
    VariantMetadata,
    normalize_unit,
)


class ValidationIssue:
    """Représente une anomalie ou un avertissement de validation."""
    def __init__(self, severity: str, message: str, context: Optional[str] = None):
        self.severity = severity  # "ERROR" ou "WARNING"
        self.message = message
        self.context = context

    def __repr__(self) -> str:
        ctx = f" [{self.context}]" if self.context else ""
        return f"{self.severity}{ctx}: {self.message}"


class ValidationReport:
    """Rapport complet de validation d'un ensemble de données ou d'une variante."""
    def __init__(self):
        self.issues: List[ValidationIssue] = []

    def add_error(self, message: str, context: Optional[str] = None) -> None:
        self.issues.append(ValidationIssue("ERROR", message, context))

    def add_warning(self, message: str, context: Optional[str] = None) -> None:
        self.issues.append(ValidationIssue("WARNING", message, context))

    @property
    def is_valid(self) -> bool:
        """Valide uniquement s'il n'y a aucune erreur critique."""
        return not any(issue.severity == "ERROR" for issue in self.issues)

    @property
    def errors(self) -> List[str]:
        return [str(i) for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> List[str]:
        return [str(i) for i in self.issues if i.severity == "WARNING"]


def validate_unit(unit_str: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    """Vérifie si une unité est valide ou convertible vers une unité canonique.
    
    Retourne (est_valide, unite_canonique, message_erreur).
    """
    if pd.isna(unit_str) or not str(unit_str).strip():
        return False, None, "Unité manquante (vide)"
    
    raw = str(unit_str).strip()
    try:
        canonical = normalize_unit(raw)
        return True, canonical, None
    except ValueError as e:
        return False, None, str(e)


def validate_quantity_row(
    row: Dict[str, Any],
    row_idx: int,
    report: ValidationReport
) -> Optional[QuantityItem]:
    """Valide une ligne individuelle de métré/quantité."""
    code_raw = row.get("code")
    designation_raw = row.get("designation")
    quantite_raw = row.get("quantite")
    unite_raw = row.get("unite")
    categorie_raw = row.get("categorie")

    ctx = f"Ligne {row_idx}"

    # Vérification du code
    if pd.isna(code_raw) or not str(code_raw).strip():
        report.add_error("Code de poste manquant ou vide", ctx)
        return None
    code = str(code_raw).strip().lower().replace(" ", "_")

    # Désignation
    designation = str(designation_raw).strip() if not pd.isna(designation_raw) else code

    # Vérification de l'unité
    is_valid_unit, canonical_unit, unit_err = validate_unit(unite_raw)
    if not is_valid_unit or canonical_unit is None:
        report.add_error(f"Unité invalide: {unit_err}", ctx)
        return None

    # Vérification de la quantité
    try:
        qty = float(quantite_raw)
        if pd.isna(qty):
            report.add_error("Quantité non définie (NaN)", ctx)
            return None
        if qty < 0:
            report.add_error(f"Quantité négative interdite ({qty})", ctx)
            return None
    except (ValueError, TypeError):
        report.add_error(f"Valeur numérique de quantité invalide: '{quantite_raw}'", ctx)
        return None

    # Catégorie
    category = QuantityCategory.DIVERS
    if not pd.isna(categorie_raw) and str(categorie_raw).strip():
        cat_str = str(categorie_raw).strip().upper()
        # Normalisation souple de la catégorie
        if cat_str in QuantityCategory.__members__:
            category = QuantityCategory[cat_str]
        elif "TERRASS" in cat_str:
            category = QuantityCategory.TERRASSEMENT
        elif "CHAUSS" in cat_str or "REVET" in cat_str:
            category = QuantityCategory.CHAUSSEE
        elif "ASSAIN" in cat_str or "DRAIN" in cat_str:
            category = QuantityCategory.ASSAINISSEMENT
        elif "OUVRAG" in cat_str or "PONT" in cat_str or "OA" in cat_str:
            category = QuantityCategory.OUVRAGES_ART
        elif "EQUIP" in cat_str or "SECURIT" in cat_str:
            category = QuantityCategory.EQUIPEMENT
        elif "ENVIRON" in cat_str:
            category = QuantityCategory.ENVIRONNEMENT
        else:
            report.add_warning(f"Catégorie inconnue '{cat_str}', classée en DIVERS", ctx)
            category = QuantityCategory.DIVERS

    return QuantityItem(
        code=code,
        designation=designation,
        category=category,
        quantity=qty,
        unit=canonical_unit,
    )


def validate_variant_metadata(
    meta_dict: Dict[str, Any],
    report: ValidationReport
) -> Optional[VariantMetadata]:
    """Valide les métadonnées de la variante routière."""
    name = meta_dict.get("nom") or meta_dict.get("nom_variante") or meta_dict.get("name")
    if not name or pd.isna(name) or not str(name).strip():
        report.add_error("Le nom de la variante est obligatoire.")
        return None
    
    name = str(name).strip()

    # Longueur totale
    raw_len = meta_dict.get("longueur_m") or meta_dict.get("longueur") or meta_dict.get("total_length_m", 0.0)
    try:
        length_m = float(raw_len)
        if length_m < 0:
            report.add_error(f"La longueur du tracé ne peut pas être négative ({length_m} m).")
            return None
        if length_m == 0:
            report.add_warning("Longueur du tracé renseignée à 0 m.")
    except (ValueError, TypeError):
        report.add_error(f"Valeur de longueur invalide: '{raw_len}'")
        return None

    # Emprise
    raw_row = meta_dict.get("emprise_m2") or meta_dict.get("emprise") or meta_dict.get("right_of_way_m2", 0.0)
    try:
        row_m2 = float(raw_row)
        if row_m2 < 0:
            report.add_error(f"L'emprise ne peut pas être négative ({row_m2} m2).")
            return None
    except (ValueError, TypeError):
        report.add_error(f"Valeur d'emprise foncière invalide: '{raw_row}'")
        return None

    # Facteurs foisonnement / compactage
    swelling = meta_dict.get("foisonnement", meta_dict.get("swelling_factor", 1.20))
    compaction = meta_dict.get("compactage", meta_dict.get("compaction_factor", 0.90))

    try:
        swelling_f = float(swelling)
        if swelling_f <= 0:
            report.add_error(f"Le coefficient de foisonnement doit être > 0 ({swelling_f}).")
            return None
    except (ValueError, TypeError):
        report.add_error(f"Coefficient de foisonnement invalide: '{swelling}'")
        return None

    try:
        compaction_f = float(compaction)
        if compaction_f <= 0:
            report.add_error(f"Le coefficient de compactage doit être > 0 ({compaction_f}).")
            return None
    except (ValueError, TypeError):
        report.add_error(f"Coefficient de compactage invalide: '{compaction}'")
        return None

    return VariantMetadata(
        name=name,
        code=str(meta_dict.get("code")) if meta_dict.get("code") and not pd.isna(meta_dict.get("code")) else None,
        description=str(meta_dict.get("description")) if meta_dict.get("description") and not pd.isna(meta_dict.get("description")) else None,
        total_length_m=length_m,
        right_of_way_m2=row_m2,
        swelling_factor=swelling_f,
        compaction_factor=compaction_f,
    )
