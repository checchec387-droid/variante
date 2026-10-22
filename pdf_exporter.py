"""Générateur de rapports officiels PDF pour les comparatifs de variantes routières."""
from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.core.models import (
    EarthworkStatus,
    UnitCostCatalog,
    Variant,
    VariantComparison,
)


class NumberedCanvas(canvas.Canvas):
    """Toile personnalisée ReportLab calculant dynamiquement le nombre total de pages 'Page X / Y'."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Ligne de séparation de bas de page
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.2 * cm, A4[0] - 1.5 * cm, 1.2 * cm)

        # Pied de page gauche et droit
        self.drawString(1.5 * cm, 0.8 * cm, "Road Variant Comparator — Outil d'aide à la décision VRD")
        page_str = f"Page {self._pageNumber} sur {page_count}"
        self.drawRightString(A4[0] - 1.5 * cm, 0.8 * cm, page_str)
        self.restoreState()


def generate_pdf_report(
    comparison: VariantComparison,
    baseline_variant: Variant,
    target_variant: Variant,
    catalog: Optional[UnitCostCatalog] = None,
    project_name: str = "Projet Routier",
    author: str = "Bureau d'Études VRD",
    warnings: Optional[List[str]] = None,
) -> bytes:
    """Génère un rapport PDF complet au format A4 avec métadonnées, synthèse, écarts et recommandations."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()

    # Définition de styles personnalisés
    style_title = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#1E293B"),
    )
    style_subtitle = ParagraphStyle(
        "DocSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748B"),
    )
    style_section = ParagraphStyle(
        "DocSection",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=10,
        spaceAfter=6,
    )
    style_cell_normal = ParagraphStyle(
        "CellNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1E293B"),
    )
    style_cell_bold = ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0F172A"),
    )
    style_cell_right = ParagraphStyle(
        "CellRight",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        alignment=2,  # Droite
        textColor=colors.HexColor("#1E293B"),
    )
    style_cell_center = ParagraphStyle(
        "CellCenter",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        alignment=1,  # Centre
        textColor=colors.HexColor("#1E293B"),
    )
    style_th = ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1,
    )

    story = []
    curr = comparison.currency or "EUR"

    # 1. En-tête principal / Cartouche
    header_data = [
        [
            Paragraph("🛣️ <b>ROAD VARIANT COMPARATOR</b>", style_title),
            Paragraph(f"<b>Date :</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}<br/><b>Auteur :</b> {author}", style_cell_normal)
        ],
        [
            Paragraph(f"<b>Projet :</b> {project_name}<br/><b>Comparatif :</b> {baseline_variant.name} <i>(Réf)</i> vs {target_variant.name} <i>(Cible)</i>", style_subtitle),
            Paragraph(f"<b>Devise :</b> {curr}", style_cell_normal)
        ]
    ]
    t_header = Table(header_data, colWidths=[12.0 * cm, 5.0 * cm])
    t_header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 10))

    # 2. Section 1 : Hypothèses et Sources
    story.append(Paragraph("1. Hypothèses Générales et Sources des Données", style_section))

    base_desc = getattr(baseline_variant.metadata, "description", "Métré exporté") or "Métré exporté"
    tgt_desc = getattr(target_variant.metadata, "description", "Métré exporté") or "Métré exporté"

    hyp_table_data = [
        [Paragraph("Paramètre / Hypothèse", style_th), Paragraph("Unité", style_th), Paragraph(f"Référence : {baseline_variant.name}", style_th), Paragraph(f"Cible : {target_variant.name}", style_th)],
        [Paragraph("Longueur du tracé", style_cell_normal), Paragraph("m", style_cell_center), Paragraph(f"{baseline_variant.metadata.total_length_m:,.0f}", style_cell_right), Paragraph(f"{target_variant.metadata.total_length_m:,.0f}", style_cell_right)],
        [Paragraph("Emprise foncière", style_cell_normal), Paragraph("m²", style_cell_center), Paragraph(f"{baseline_variant.metadata.right_of_way_m2:,.0f}", style_cell_right), Paragraph(f"{target_variant.metadata.right_of_way_m2:,.0f}", style_cell_right)],
        [Paragraph("Coeff. Foisonnement", style_cell_normal), Paragraph("-", style_cell_center), Paragraph(f"{baseline_variant.metadata.swelling_factor:.2f}", style_cell_right), Paragraph(f"{target_variant.metadata.swelling_factor:.2f}", style_cell_right)],
        [Paragraph("Coeff. Compactage", style_cell_normal), Paragraph("-", style_cell_center), Paragraph(f"{baseline_variant.metadata.compaction_factor:.2f}", style_cell_right), Paragraph(f"{target_variant.metadata.compaction_factor:.2f}", style_cell_right)],
        [Paragraph("Source des données", style_cell_normal), Paragraph("-", style_cell_center), Paragraph(base_desc, style_cell_normal), Paragraph(tgt_desc, style_cell_normal)],
    ]
    t_hyp = Table(hyp_table_data, colWidths=[6.0 * cm, 2.0 * cm, 4.5 * cm, 4.5 * cm])
    t_hyp.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_hyp)
    story.append(Spacer(1, 10))

    # 3. Section 2 : Synthèse Comparative et Écarts
    story.append(Paragraph("2. Synthèse Comparative des Indicateurs Clés", style_section))

    b_bal = comparison.baseline_earthwork
    t_bal = comparison.target_earthwork

    syn_data = [
        [
            Paragraph("Indicateur Clé", style_th),
            Paragraph("Unité", style_th),
            Paragraph(f"Réf ({baseline_variant.name})", style_th),
            Paragraph(f"Cible ({target_variant.name})", style_th),
            Paragraph("Écart Absolu (Δ)", style_th),
            Paragraph("Écart Relatif (%)", style_th),
        ],
        [
            Paragraph("Longueur d'axe", style_cell_normal),
            Paragraph("m", style_cell_center),
            Paragraph(f"{comparison.baseline_length_m:,.0f}", style_cell_right),
            Paragraph(f"{comparison.target_length_m:,.0f}", style_cell_right),
            Paragraph(f"{comparison.delta_length_m:+,.0f}", style_cell_right),
            Paragraph(f"{comparison.delta_length_percent:+.1f}%" if comparison.delta_length_percent is not None else "-", style_cell_right),
        ],
        [
            Paragraph("Emprise au sol", style_cell_normal),
            Paragraph("m²", style_cell_center),
            Paragraph(f"{comparison.baseline_right_of_way_m2:,.0f}", style_cell_right),
            Paragraph(f"{comparison.target_right_of_way_m2:,.0f}", style_cell_right),
            Paragraph(f"{comparison.delta_right_of_way_m2:+,.0f}", style_cell_right),
            Paragraph(f"{comparison.delta_right_of_way_percent:+.1f}%" if comparison.delta_right_of_way_percent is not None else "-", style_cell_right),
        ],
        [
            Paragraph("Déblais totaux bruts", style_cell_normal),
            Paragraph("m³", style_cell_center),
            Paragraph(f"{b_bal.cut_total_m3:,.0f}", style_cell_right),
            Paragraph(f"{t_bal.cut_total_m3:,.0f}", style_cell_right),
            Paragraph(f"{comparison.delta_cut_m3:+,.0f}", style_cell_right),
            Paragraph(f"{((t_bal.cut_total_m3 - b_bal.cut_total_m3) / b_bal.cut_total_m3 * 100):+.1f}%" if b_bal.cut_total_m3 > 0 else "-", style_cell_right),
        ],
        [
            Paragraph("Remblais compactés", style_cell_normal),
            Paragraph("m³", style_cell_center),
            Paragraph(f"{b_bal.fill_total_m3:,.0f}", style_cell_right),
            Paragraph(f"{t_bal.fill_total_m3:,.0f}", style_cell_right),
            Paragraph(f"{comparison.delta_fill_m3:+,.0f}", style_cell_right),
            Paragraph(f"{((t_bal.fill_total_m3 - b_bal.fill_total_m3) / b_bal.fill_total_m3 * 100):+.1f}%" if b_bal.fill_total_m3 > 0 else "-", style_cell_right),
        ],
        [
            Paragraph("Solde net des terres", style_cell_bold),
            Paragraph("m³", style_cell_center),
            Paragraph(f"{b_bal.net_balance_m3:+,.0f}", style_cell_right),
            Paragraph(f"{t_bal.net_balance_m3:+,.0f}", style_cell_right),
            Paragraph(f"{t_bal.net_balance_m3 - b_bal.net_balance_m3:+,.0f}", style_cell_right),
            Paragraph(f"{t_bal.status.value}", style_cell_center),
        ],
    ]

    if comparison.baseline_total_cost is not None and comparison.target_total_cost is not None:
        syn_data.append([
            Paragraph("<b>Coût Total Estimé HT</b>", style_cell_bold),
            Paragraph(curr, style_cell_center),
            Paragraph(f"<b>{comparison.baseline_total_cost:,.2f}</b>", style_cell_right),
            Paragraph(f"<b>{comparison.target_total_cost:,.2f}</b>", style_cell_right),
            Paragraph(f"<b>{comparison.delta_abs_total_cost:+,.2f}</b>", style_cell_right),
            Paragraph(f"<b>{comparison.delta_rel_total_cost_percent:+.2f}%</b>" if comparison.delta_rel_total_cost_percent is not None else "-", style_cell_right),
        ])

    t_syn = Table(syn_data, colWidths=[4.2 * cm, 1.3 * cm, 2.9 * cm, 2.9 * cm, 2.9 * cm, 2.8 * cm])
    t_syn.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2 if comparison.baseline_total_cost else -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_syn)
    story.append(Spacer(1, 10))

    # 4. Section 3 : Détail des Postes (Métré comparatif)
    story.append(Paragraph("3. Analyse Détaillée des Écarts Poste par Poste", style_section))

    det_data = [
        [
            Paragraph("Lot / Désignation", style_th),
            Paragraph("Unité", style_th),
            Paragraph(f"Qté ({comparison.baseline_name})", style_th),
            Paragraph(f"Qté ({comparison.target_name})", style_th),
            Paragraph("Δ Quantité", style_th),
            Paragraph(f"Montant Réf ({curr})", style_th),
            Paragraph(f"Montant Cible ({curr})", style_th),
            Paragraph(f"Δ Coût ({curr})", style_th),
        ]
    ]

    for it in comparison.items:
        det_data.append([
            Paragraph(f"<b>[{it.category.value[:4]}]</b> {it.designation[:30]}", style_cell_normal),
            Paragraph(it.unit, style_cell_center),
            Paragraph(f"{it.baseline_qty:,.1f}", style_cell_right),
            Paragraph(f"{it.target_qty:,.1f}", style_cell_right),
            Paragraph(f"{it.delta_abs_qty:+,.1f}" if it.delta_abs_qty is not None else ("Incomp." if it.unit_mismatch else "-"), style_cell_right),
            Paragraph(f"{it.baseline_cost:,.0f}" if it.baseline_cost is not None else "-", style_cell_right),
            Paragraph(f"{it.target_cost:,.0f}" if it.target_cost is not None else "-", style_cell_right),
            Paragraph(f"{it.delta_abs_cost:+,.0f}" if it.delta_abs_cost is not None else "-", style_cell_right),
        ])

    # Ligne total postes
    if comparison.baseline_total_cost is not None:
        det_data.append([
            Paragraph("<b>TOTAL GÉNÉRAL HT</b>", style_cell_bold),
            Paragraph("-", style_cell_center),
            Paragraph("-", style_cell_center),
            Paragraph("-", style_cell_center),
            Paragraph("-", style_cell_center),
            Paragraph(f"<b>{comparison.baseline_total_cost:,.0f}</b>", style_cell_right),
            Paragraph(f"<b>{comparison.target_total_cost:,.0f}</b>", style_cell_right),
            Paragraph(f"<b>{comparison.delta_abs_total_cost:+,.0f}</b>", style_cell_right),
        ])

    t_det = Table(det_data, colWidths=[5.0 * cm, 1.2 * cm, 2.0 * cm, 2.0 * cm, 2.0 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm], repeatRows=1)
    t_det.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2 if comparison.baseline_total_cost else -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_det)
    story.append(Spacer(1, 10))

    # 5. Section 4 : Avertissements et Recommandations
    story.append(Paragraph("4. Avertissements Techniques et Recommandations", style_section))

    all_warnings = list(warnings or [])
    for um in comparison.unit_mismatches:
        if um not in all_warnings:
            all_warnings.append(um)
    if t_bal.status == EarthworkStatus.DEFICITAIRE:
        all_warnings.append(f"Déficit en remblai de {t_bal.net_balance_m3:,.0f} m³ sur la variante cible : prévoir des zones d'emprunt.")
    elif t_bal.status == EarthworkStatus.EXCEDENTAIRE:
        all_warnings.append(f"Excédent de déblais de +{t_bal.net_balance_m3:,.0f} m³ sur la variante cible : prévoir des dépôts définitifs.")

    if comparison.delta_abs_total_cost is not None:
        if comparison.delta_abs_total_cost < 0:
            all_warnings.append(f"Économie financière globale de {abs(comparison.delta_abs_total_cost):,.2f} {curr} ({comparison.delta_rel_total_cost_percent:+.2f}%) en faveur de la variante {target_variant.name}.")
        elif comparison.delta_abs_total_cost > 0:
            all_warnings.append(f"Surcoût financier global de +{comparison.delta_abs_total_cost:,.2f} {curr} ({comparison.delta_rel_total_cost_percent:+.2f}%) pour la variante {target_variant.name}.")

    warn_elements = []
    for w in all_warnings:
        warn_elements.append(Paragraph(f"• {w}", style_cell_normal))
        warn_elements.append(Spacer(1, 2))

    story.append(KeepTogether(warn_elements))

    # Construction du document avec NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()
