"""Parsers for Excel, CSV, and Civil 3D tabular exports."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd

from src.core.models import (
    CanonicalUnit,
    QuantityCategory,
    QuantityItem,
    UnitCostCatalog,
    UnitPrice,
    Variant,
    VariantMetadata,
)
from src.io.validators import (
    ValidationReport,
    validate_quantity_row,
    validate_variant_metadata,
)


class DataParsingError(Exception):
    """Exception levée en cas d'échec critique du parsing des données."""
    def __init__(self, message: str, report: Optional[ValidationReport] = None):
        super().__init__(message)
        self.report = report


def _normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les noms de colonnes : minuscules, suppression des accents et espaces."""
    mapping = {}
    for col in df.columns:
        c = str(col).strip().lower()
        c = c.replace("é", "e").replace("è", "e").replace("ê", "e")
        c = c.replace("à", "a").replace("ç", "c")
        c = c.replace(" ", "_").replace("-", "_")
        # Alias fréquents
        if c in ["quantity", "qty", "volume", "valeur"]:
            c = "quantite"
        elif c in ["unit", "unites", "u"]:
            c = "unite"
        elif c in ["libelle", "description", "item"]:
            c = "designation"
        elif c in ["category", "famille", "lot"]:
            c = "categorie"
        elif c in ["prix", "pu", "prix_ht", "unit_price"]:
            c = "prix_unitaire"
        mapping[col] = c
    return df.rename(columns=mapping)


def parse_metadata_sheet(df_meta: pd.DataFrame) -> Dict[str, Any]:
    """Parse une feuille clé-valeur de métadonnées."""
    meta = {}
    if df_meta.shape[1] >= 2:
        for _, row in df_meta.iterrows():
            k = str(row.iloc[0]).strip().lower()
            k = k.replace("é", "e").replace("è", "e").replace(" ", "_")
            v = row.iloc[1]
            if not pd.isna(k) and k:
                meta[k] = v
    return meta


def parse_variant_excel(
    file_path_or_bytes: Union[str, Path, io.BytesIO],
    default_name: str = "Variante"
) -> Tuple[Variant, ValidationReport]:
    """Charge une variante à partir d'un classeur Excel.
    
    Supporte :
    - Soit un classeur multi-onglets ('Metadonnees' et 'Quantites')
    - Soit un onglet unique tabulaire.
    """
    report = ValidationReport()
    excel_file = pd.ExcelFile(file_path_or_bytes)
    sheet_names = [s.strip().lower() for s in excel_file.sheet_names]

    metadata_dict: Dict[str, Any] = {"nom": default_name}
    df_quantities: Optional[pd.DataFrame] = None

    # 1. Recherche d'un onglet de métadonnées
    meta_sheet_name = None
    for name in excel_file.sheet_names:
        low = name.strip().lower()
        if any(kw in low for kw in ["meta", "info", "general"]):
            meta_sheet_name = name
            break

    if meta_sheet_name:
        df_meta = pd.read_excel(file_path_or_bytes, sheet_name=meta_sheet_name, header=None)
        metadata_dict.update(parse_metadata_sheet(df_meta))

    # 2. Recherche de l'onglet des quantités (en excluant formellement l'onglet de métadonnées)
    qty_sheet_name = None
    for name in excel_file.sheet_names:
        if name == meta_sheet_name:
            continue
        low = name.strip().lower()
        if any(kw in low for kw in ["quantit", "metre", "cubature", "donnees", "data"]):
            qty_sheet_name = name
            break

    if qty_sheet_name:
        df_quantities = pd.read_excel(file_path_or_bytes, sheet_name=qty_sheet_name)
    else:
        # Prendre le premier onglet qui n'est pas l'onglet de métadonnées
        candidates = [s for s in excel_file.sheet_names if s != meta_sheet_name]
        if candidates:
            df_quantities = pd.read_excel(file_path_or_bytes, sheet_name=candidates[0])
        else:
            raise DataParsingError("Aucun onglet de quantités trouvé dans le fichier Excel.", report)

    # 3. Extraction et validation
    return _build_variant_from_dataframe(df_quantities, metadata_dict, report, default_name)


def parse_variant_csv(
    file_path_or_bytes: Union[str, Path, io.BytesIO, io.StringIO],
    default_name: str = "Variante",
    delimiter: Optional[str] = None
) -> Tuple[Variant, ValidationReport]:
    """Charge une variante à partir d'un fichier CSV tabulaire."""
    report = ValidationReport()

    # Tentative de détection du délimiteur si non fourni
    if delimiter is None:
        try:
            df_quantities = pd.read_csv(file_path_or_bytes, sep=None, engine="python")
        except Exception:
            # Fallback point-virgule puis virgule
            if isinstance(file_path_or_bytes, (io.BytesIO, io.StringIO)):
                file_path_or_bytes.seek(0)
            try:
                df_quantities = pd.read_csv(file_path_or_bytes, sep=";")
            except Exception:
                if isinstance(file_path_or_bytes, (io.BytesIO, io.StringIO)):
                    file_path_or_bytes.seek(0)
                df_quantities = pd.read_csv(file_path_or_bytes, sep=",")
    else:
        df_quantities = pd.read_csv(file_path_or_bytes, sep=delimiter)

    metadata_dict: Dict[str, Any] = {"nom": default_name}
    return _build_variant_from_dataframe(df_quantities, metadata_dict, report, default_name)


def _build_variant_from_dataframe(
    df: pd.DataFrame,
    metadata_dict: Dict[str, Any],
    report: ValidationReport,
    fallback_name: str
) -> Tuple[Variant, ValidationReport]:
    """Convertit un DataFrame normalisé en objet Variant après validation."""
    df_clean = _normalize_column_names(df)

    # Vérification des colonnes obligatoires
    required_cols = {"code", "quantite", "unite"}
    missing = required_cols - set(df_clean.columns)
    if missing:
        report.add_error(f"Colonnes obligatoires manquantes dans les données : {', '.join(missing)}")
        raise DataParsingError(f"Colonnes obligatoires manquantes : {missing}", report)

    # Si le nom n'est pas dans les métadonnées, tenter de le trouver dans une colonne ou utiliser le fallback
    if "nom" not in metadata_dict or not metadata_dict["nom"]:
        metadata_dict["nom"] = fallback_name

    meta = validate_variant_metadata(metadata_dict, report)
    if meta is None:
        raise DataParsingError("Métadonnées de la variante invalides.", report)

    variant = Variant(metadata=meta)

    # Itération sur les lignes
    seen_codes = set()
    for idx, row in df_clean.iterrows():
        row_dict = row.to_dict()
        item = validate_quantity_row(row_dict, int(idx) + 1, report)
        if item is not None:
            if item.code in seen_codes:
                report.add_warning(
                    f"Code '{item.code}' présent plusieurs fois. La valeur de la ligne {idx + 1} remplace la précédente.",
                    f"Ligne {idx + 1}"
                )
            seen_codes.add(item.code)
            variant.add_item(item)

    if not variant.items:
        report.add_error("Aucun poste quantitatif valide n'a pu être extrait du fichier.")
        raise DataParsingError("Fichier vide ou sans postes valides.", report)

    return variant, report


def parse_multi_variant_matrix(
    file_path_or_bytes: Union[str, Path, io.BytesIO],
    file_type: str = "excel"
) -> Tuple[List[Variant], ValidationReport]:
    """Parse un classeur ou fichier CSV contenant plusieurs variantes en colonnes.
    
    Structure attendue du tableau :
    Colonnes : [code, designation, categorie, unite, Variante 1, Variante 2, ...]
    """
    report = ValidationReport()

    if file_type.lower() in ["excel", "xlsx", "xls"]:
        df_raw = pd.read_excel(file_path_or_bytes)
    else:
        df_raw = pd.read_csv(file_path_or_bytes, sep=None, engine="python")

    df = _normalize_column_names(df_raw)

    base_cols = {"code", "designation", "categorie", "unite"}
    found_base = base_cols.intersection(set(df.columns))
    if not {"code", "unite"}.issubset(found_base):
        report.add_error("Le tableau multi-variantes doit comporter au moins les colonnes 'code' et 'unite'.")
        raise DataParsingError("Colonnes de base 'code' et 'unite' introuvables.", report)

    # Les colonnes restantes sont traitées comme des noms de variantes
    reserved = {"code", "designation", "categorie", "unite", "quantite"}
    variant_cols = [c for c in df.columns if c not in reserved and not c.startswith("unnamed")]

    if not variant_cols:
        report.add_error("Aucune colonne de variante détectée.")
        raise DataParsingError("Aucune variante identifiée dans les colonnes.", report)

    variants: List[Variant] = []

    for v_col in variant_cols:
        v_name = str(v_col).replace("_", " ").title()
        meta = VariantMetadata(
            name=v_name,
            total_length_m=1000.0,  # Valeur par défaut si non spécifié
            right_of_way_m2=20000.0,
            swelling_factor=1.20,
            compaction_factor=0.90,
        )
        v = Variant(metadata=meta)

        for idx, row in df.iterrows():
            qty_val = row[v_col]
            if pd.isna(qty_val):
                qty_val = 0.0

            sub_dict = {
                "code": row.get("code"),
                "designation": row.get("designation", row.get("code")),
                "categorie": row.get("categorie", "DIVERS"),
                "unite": row.get("unite"),
                "quantite": qty_val,
            }
            item = validate_quantity_row(sub_dict, int(idx) + 1, report)
            if item is not None:
                v.add_item(item)

        variants.append(v)

    return variants, report


def parse_cost_catalog(
    file_path_or_bytes: Union[str, Path, io.BytesIO],
    file_type: str = "excel",
    currency: str = "EUR"
) -> Tuple[UnitCostCatalog, ValidationReport]:
    """Charge un catalogue de prix unitaires (BPU) depuis Excel ou CSV."""
    report = ValidationReport()

    if file_type.lower() in ["excel", "xlsx", "xls"]:
        df_raw = pd.read_excel(file_path_or_bytes)
    else:
        df_raw = pd.read_csv(file_path_or_bytes, sep=None, engine="python")

    df = _normalize_column_names(df_raw)

    required = {"code", "prix_unitaire", "unite"}
    missing = required - set(df.columns)
    if missing:
        report.add_error(f"Colonnes BPU manquantes : {', '.join(missing)}")
        raise DataParsingError(f"Colonnes BPU obligatoires manquantes : {missing}", report)

    catalog = UnitCostCatalog(currency=currency)

    for idx, row in df.iterrows():
        ctx = f"BPU Ligne {idx + 1}"
        code_raw = row.get("code")
        if pd.isna(code_raw) or not str(code_raw).strip():
            continue

        price_raw = row.get("prix_unitaire")
        try:
            price = float(price_raw)
            if price < 0:
                report.add_error(f"Prix unitaire négatif ({price}) interdit", ctx)
                continue
        except (ValueError, TypeError):
            report.add_error(f"Prix invalide '{price_raw}'", ctx)
            continue

        desig_raw = row.get("designation", code_raw)
        designation = str(desig_raw).strip() if not pd.isna(desig_raw) else str(code_raw)

        unit_raw = row.get("unite", "u")

        try:
            unit_price = UnitPrice(
                code=str(code_raw),
                designation=designation,
                unit=str(unit_raw),
                price=price,
            )
            catalog.add_price(unit_price)
        except Exception as e:
            report.add_error(f"Erreur sur le prix {code_raw}: {e}", ctx)

    return catalog, report
