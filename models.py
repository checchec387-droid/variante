"""Domain models and data structures for Road Variant Comparator."""
from __future__ import annotations

import math
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class CanonicalUnit(str, Enum):
    """Unités standard autorisées dans les études routières."""
    METER = "m"
    SQUARE_METER = "m2"
    CUBIC_METER = "m3"
    LINEAR_METER = "ml"
    TON = "t"
    UNIT = "u"
    KILOMETER = "km"
    HECTARE = "ha"
    LUMP_SUM = "ff"  # Forfait


# Mappage de tolérance pour normalisation automatique des unités
UNIT_ALIASES: Dict[str, CanonicalUnit] = {
    "m": CanonicalUnit.METER,
    "metre": CanonicalUnit.METER,
    "mètre": CanonicalUnit.METER,
    "meter": CanonicalUnit.METER,
    "m2": CanonicalUnit.SQUARE_METER,
    "m²": CanonicalUnit.SQUARE_METER,
    "sqm": CanonicalUnit.SQUARE_METER,
    "m3": CanonicalUnit.CUBIC_METER,
    "m³": CanonicalUnit.CUBIC_METER,
    "cum": CanonicalUnit.CUBIC_METER,
    "ml": CanonicalUnit.LINEAR_METER,
    "m.l.": CanonicalUnit.LINEAR_METER,
    "m.l": CanonicalUnit.LINEAR_METER,
    "t": CanonicalUnit.TON,
    "tonne": CanonicalUnit.TON,
    "tonnes": CanonicalUnit.TON,
    "ton": CanonicalUnit.TON,
    "u": CanonicalUnit.UNIT,
    "unite": CanonicalUnit.UNIT,
    "unité": CanonicalUnit.UNIT,
    "unit": CanonicalUnit.UNIT,
    "km": CanonicalUnit.KILOMETER,
    "ha": CanonicalUnit.HECTARE,
    "ff": CanonicalUnit.LUMP_SUM,
    "forfait": CanonicalUnit.LUMP_SUM,
    "ens": CanonicalUnit.LUMP_SUM,
}


def normalize_unit(raw_unit: str) -> str:
    """Normalise une chaîne d'unité vers sa valeur canonique.
    
    Lève ValueError si l'unité n'est pas reconnue.
    """
    cleaned = raw_unit.strip().lower()
    if cleaned in UNIT_ALIASES:
        return UNIT_ALIASES[cleaned].value
    raise ValueError(
        f"Unité inconnue ou non supportée: '{raw_unit}'. "
        f"Unités supportées: {', '.join(sorted(UNIT_ALIASES.keys()))}"
    )


class QuantityCategory(str, Enum):
    """Grandes familles de postes de travaux routiers."""
    TERRASSEMENT = "TERRASSEMENT"
    CHAUSSEE = "CHAUSSEE"
    ASSAINISSEMENT = "ASSAINISSEMENT"
    OUVRAGES_ART = "OUVRAGES_ART"
    EQUIPEMENT = "EQUIPEMENT"
    ENVIRONNEMENT = "ENVIRONNEMENT"
    DIVERS = "DIVERS"


class QuantityItem(BaseModel):
    """Poste quantitatif individuel d'une variante routière."""
    code: str = Field(..., min_length=1, description="Code unique de la prestation (ex: deblai_meuble, bbd_010)")
    designation: str = Field(..., min_length=1, description="Libellé explicite du poste")
    category: QuantityCategory = Field(default=QuantityCategory.DIVERS, description="Famille du poste")
    quantity: float = Field(..., ge=0.0, description="Quantité mesurée (doit être >= 0)")
    unit: str = Field(..., description="Unité de mesure (canonique)")

    @field_validator("code")
    @classmethod
    def clean_code(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_")

    @field_validator("unit")
    @classmethod
    def validate_and_normalize_unit(cls, v: str) -> str:
        return normalize_unit(v)


class VariantMetadata(BaseModel):
    """Métadonnées descriptives et géométriques d'une variante routière."""
    name: str = Field(..., min_length=1, description="Nom d'identification de la variante (ex: Variante Nord)")
    code: Optional[str] = Field(None, description="Code court (ex: V1, VAR-A)")
    description: Optional[str] = Field(None, description="Notes explicatives et contexte")
    total_length_m: float = Field(..., ge=0.0, description="Longueur totale de l'axe routier en mètres")
    right_of_way_m2: float = Field(..., ge=0.0, description="Emprise foncière nécessaire en mètres carrés")
    swelling_factor: float = Field(
        default=1.20,
        gt=0.0,
        description="Coefficient de foisonnement des déblais (ex: 1.20 pour +20% de volume meuble)"
    )
    compaction_factor: float = Field(
        default=0.90,
        gt=0.0,
        description="Coefficient de compactage / contre-foisonnement pour mise en remblai (ex: 0.90)"
    )


class Variant(BaseModel):
    """Représentation complète d'une variante de projet routier."""
    metadata: VariantMetadata
    items: Dict[str, QuantityItem] = Field(default_factory=dict)

    def add_item(self, item: QuantityItem) -> None:
        """Ajoute ou remplace un poste de quantité."""
        self.items[item.code] = item

    def get_quantity(self, code: str) -> float:
        """Retourne la quantité associée à un code, ou 0.0 si absent."""
        cleaned_code = code.strip().lower().replace(" ", "_")
        item = self.items.get(cleaned_code)
        return item.quantity if item else 0.0

    @property
    def name(self) -> str:
        return self.metadata.name


class UnitPrice(BaseModel):
    """Prix unitaire d'un bordereau de prix."""
    code: str = Field(..., min_length=1)
    designation: str = Field(..., min_length=1)
    unit: str
    price: float = Field(..., ge=0.0, description="Prix unitaire hors taxes")
    category: Optional[QuantityCategory] = None

    @field_validator("code")
    @classmethod
    def clean_code(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_")

    @field_validator("unit")
    @classmethod
    def validate_and_normalize_unit(cls, v: str) -> str:
        return normalize_unit(v)


class UnitCostCatalog(BaseModel):
    """Catalogue ou Bordereau des Prix Unitaires (BPU)."""
    currency: str = Field(default="EUR", description="Devise monétaire (ex: EUR, DZD, USD)")
    prices: Dict[str, UnitPrice] = Field(default_factory=dict)

    def add_price(self, price_item: UnitPrice) -> None:
        self.prices[price_item.code] = price_item

    def get_price(self, code: str) -> Optional[float]:
        cleaned_code = code.strip().lower().replace(" ", "_")
        item = self.prices.get(cleaned_code)
        return item.price if item else None

    def get_price_item(self, code: str) -> Optional[UnitPrice]:
        """Retourne l'objet UnitPrice complet comprenant le prix et l'unité."""
        cleaned_code = code.strip().lower().replace(" ", "_")
        return self.prices.get(cleaned_code)


class EarthworkStatus(str, Enum):
    """Statut du mouvement des terres."""
    EXCEDENTAIRE = "EXCEDENTAIRE"    # Les déblais réutilisables dépassent les besoins en remblai (mise en dépôt)
    DEFICITAIRE = "DEFICITAIRE"      # Manque de remblais (emprunt extérieur nécessaire)
    EQUILIBRE = "EQUILIBRE"          # Équilibre parfait ou dans le seuil de tolérance


class EarthworkBalance(BaseModel):
    """Bilan synthétique des terrassements d'une variante."""
    cut_total_m3: float = Field(..., ge=0.0, description="Volume total brut des déblais (m3 en place)")
    fill_total_m3: float = Field(..., ge=0.0, description="Volume total des remblais (m3 compacté)")
    usable_cut_m3: float = Field(..., ge=0.0, description="Déblais réutilisables après application du coefficient de réutilisation")
    net_balance_m3: float = Field(..., description="Excédent (+) ou Déficit (-) en m3")
    status: EarthworkStatus


class ItemComparison(BaseModel):
    """Comparaison détaillée d'un poste élémentaire entre deux variantes."""
    code: str
    designation: str
    category: QuantityCategory
    unit: str
    baseline_qty: float
    target_qty: float
    delta_abs_qty: Optional[float] = None               # target_qty - baseline_qty (None si unités incompatibles)
    delta_rel_qty_percent: Optional[float] = None       # ((target - base) / base) * 100
    unit_price: Optional[float] = None
    baseline_cost: Optional[float] = None
    target_cost: Optional[float] = None
    delta_abs_cost: Optional[float] = None
    delta_rel_cost_percent: Optional[float] = None
    unit_mismatch: bool = False                         # Vrai si incohérence d'unité entre variantes
    warning: Optional[str] = None                       # Message d'avertissement spécifique à ce poste


class CategoryCostSummary(BaseModel):
    """Synthèse financière par famille de travaux."""
    category: QuantityCategory
    baseline_cost: float
    target_cost: float
    delta_abs_cost: float
    delta_rel_cost_percent: Optional[float] = None


class VariantComparison(BaseModel):
    """Résultat complet de la comparaison entre une variante de référence et une variante cible."""
    baseline_name: str
    target_name: str
    items: List[ItemComparison]
    
    # Écarts géométriques
    baseline_length_m: float
    target_length_m: float
    delta_length_m: float
    delta_length_percent: Optional[float] = None

    baseline_right_of_way_m2: float
    target_right_of_way_m2: float
    delta_right_of_way_m2: float
    delta_right_of_way_percent: Optional[float] = None

    # Bilans de terrassement
    baseline_earthwork: EarthworkBalance
    target_earthwork: EarthworkBalance
    delta_cut_m3: float
    delta_fill_m3: float

    # Bilan financier global (si BPU fourni)
    currency: Optional[str] = None
    baseline_total_cost: Optional[float] = None
    target_total_cost: Optional[float] = None
    delta_abs_total_cost: Optional[float] = None
    delta_rel_total_cost_percent: Optional[float] = None
    category_summaries: List[CategoryCostSummary] = Field(default_factory=list)

    # Incohérences d'unités détectées
    unit_mismatches: List[str] = Field(default_factory=list)
