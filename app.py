"""Point d'entrée principal de l'application Streamlit Road Variant Comparator."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st

from src.core.calculator import (
    calculate_earthwork_balance,
    calculate_variant_total_cost,
    compare_variants,
)
from src.core.models import (
    EarthworkStatus,
    QuantityCategory,
    QuantityItem,
    UnitCostCatalog,
    UnitPrice,
    Variant,
    VariantMetadata,
)
from src.io.civil3d_parser import parse_civil3d_volume_report
from src.io.parsers import (
    DataParsingError,
    parse_cost_catalog,
    parse_multi_variant_matrix,
    parse_variant_csv,
    parse_variant_excel,
)
from src.reporting.excel_exporter import generate_excel_report
from src.reporting.pdf_exporter import generate_pdf_report
from src.ui.components import (
    format_comparison_dataframe,
    render_comparison_summary_kpis,
    render_header,
    render_variant_kpi_cards,
)
from src.ui.plots import (
    plot_cost_breakdown_by_category,
    plot_deltas_tornado,
    plot_earthwork_comparison,
    plot_total_costs_bar,
)
from src.ui.state import (
    add_log,
    add_variant_to_state,
    clear_all_data,
    init_session_state,
    load_demo_dataset,
    remove_variant_from_state,
    set_catalog_in_state,
)

# Configuration de la page
st.set_page_config(
    page_title="Road Variant Comparator",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialisation de l'état
init_session_state()

# Rendu de l'en-tête principal
render_header()

# ==============================================================================
# BARRE LATÉRALE (SIDEBAR) : Paramètres globaux, baseline et statut
# ==============================================================================
with st.sidebar:
    st.subheader("⚙️ Pilotage du Projet")

    # Boutons d'action rapide
    col_demo, col_reset = st.columns(2)
    with col_demo:
        if st.button("🚀 Charger Démo", use_container_width=True, help="Charge un jeu certifié de 2 variantes + BPU"):
            if load_demo_dataset():
                st.success("Données de démo chargées !")
                st.rerun()
            else:
                st.error("Fichiers de démo introuvables.")
    with col_reset:
        if st.button("🗑️ Vider tout", use_container_width=True, help="Efface toutes les variantes en mémoire"):
            clear_all_data()
            st.rerun()

    st.divider()

    # Sélection de la variante de référence (Baseline)
    variants: Dict[str, Variant] = st.session_state.variants
    variant_names = list(variants.keys())

    if variant_names:
        current_baseline = st.session_state.baseline_name
        idx = variant_names.index(current_baseline) if current_baseline in variant_names else 0
        selected_baseline = st.selectbox(
            "📌 Variante de référence (Baseline) :",
            options=variant_names,
            index=idx,
            help="Toutes les comparaisons et deltas (%) seront calculés par rapport à cette variante."
        )
        if selected_baseline != st.session_state.baseline_name:
            st.session_state.baseline_name = selected_baseline
            add_log(f"Nouvelle variante de référence : '{selected_baseline}'")
            st.rerun()
    else:
        st.info("Aucune variante chargée. Importez vos données ou utilisez le bouton 'Charger Démo'.")

    # Synthèse de session
    st.divider()
    st.caption("📊 État de la session :")
    st.write(f"- Variantes en mémoire : **{len(variants)}**")
    catalog: Optional[UnitCostCatalog] = st.session_state.catalog
    if catalog:
        st.write(f"- BPU actif : **{len(catalog.prices)} prix** ({catalog.currency})")
    else:
        st.write("- BPU actif : *Non configuré*")

    # Journal d'activité
    with st.expander("📜 Journal des opérations", expanded=False):
        logs = st.session_state.get("activity_logs", [])
        if logs:
            for l in logs[:15]:
                st.caption(f"• {l}")
        else:
            st.caption("Aucune action enregistrée.")


# ==============================================================================
# CORPS DE L'APPLICATION : ONGLETS PRINCIPAUX
# ==============================================================================
tab_import, tab_bpu, tab_compare, tab_finance, tab_reports = st.tabs([
    "📁 1. Importation & Données",
    "💰 2. Bordereau des Prix (BPU)",
    "⚖️ 3. Comparatif & Terrassements",
    "📊 4. Analyse Financière & Décision",
    "📑 5. Rapports & Exports (Excel / PDF)",
])

# ------------------------------------------------------------------------------
# ONGLET 1 : IMPORTATION DES DONNÉES
# ------------------------------------------------------------------------------
with tab_import:
    st.subheader("📥 Importer de nouvelles données de variantes")

    col_up_mode, col_up_file = st.columns([1, 2])

    with col_up_mode:
        import_type = st.radio(
            "Format d'importation :",
            options=[
                "Métré standard (Excel / CSV)",
                "Matrice multi-variantes (Excel / CSV)",
                "Cubatures Autodesk Civil 3D (CSV)",
            ],
            help="Sélectionnez le type de fichier source exporté depuis vos logiciels de CAO/VRD."
        )

    with col_up_file:
        uploaded_file = st.file_uploader(
            "Sélectionner un fichier sur votre poste :",
            type=["csv", "xlsx", "xls"],
            help="Glissez-déposez votre fichier de métré ou de cubature."
        )

    # Paramètres additionnels de tracé
    if uploaded_file is not None:
        with st.expander("🛠️ Paramètres géométriques et géotechniques du tracé", expanded=True):
            p1, p2, p3, p4 = st.columns(4)
            with p1:
                input_name = st.text_input(
                    "Nom de la variante :",
                    value=Path(uploaded_file.name).stem.replace("_", " ").title()
                )
            with p2:
                input_length = st.number_input(
                    "Longueur totale du tracé (m) :",
                    min_value=0.0,
                    value=2500.0,
                    step=50.0
                )
            with p3:
                input_row = st.number_input(
                    "Emprise foncière (m²) :",
                    min_value=0.0,
                    value=50000.0,
                    step=500.0
                )
            with p4:
                input_swelling = st.number_input(
                    "Coeff. Foisonnement :",
                    min_value=0.5,
                    max_value=2.0,
                    value=1.20,
                    step=0.05
                )

        # Bouton réel d'importation
        if st.button("🚀 Valider et Importer la variante", type="primary"):
            try:
                file_bytes = io.BytesIO(uploaded_file.getvalue())
                is_excel = uploaded_file.name.lower().endswith((".xlsx", ".xls"))

                if import_type == "Métré standard (Excel / CSV)":
                    if is_excel:
                        var, report = parse_variant_excel(file_bytes, default_name=input_name)
                    else:
                        var, report = parse_variant_csv(file_bytes, default_name=input_name)
                    
                    # Mise à jour des métadonnées saisies si non définies dans le fichier
                    if var.metadata.total_length_m == 0:
                        var.metadata.total_length_m = input_length
                    if var.metadata.right_of_way_m2 == 0:
                        var.metadata.right_of_way_m2 = input_row
                    var.metadata.swelling_factor = input_swelling

                    add_variant_to_state(var)
                    st.success(f"Variante '{var.name}' importée avec succès ({len(var.items)} postes) !")
                    if report.warnings:
                        st.warning("Avertissements : " + " | ".join(report.warnings))
                    st.rerun()

                elif import_type == "Matrice multi-variantes (Excel / CSV)":
                    file_kind = "excel" if is_excel else "csv"
                    variants_list, report = parse_multi_variant_matrix(file_bytes, file_type=file_kind)
                    for v in variants_list:
                        add_variant_to_state(v)
                    st.success(f"{len(variants_list)} variantes importées avec succès !")
                    st.rerun()

                elif import_type == "Cubatures Autodesk Civil 3D (CSV)":
                    file_kind = "excel" if is_excel else "csv"
                    var, report = parse_civil3d_volume_report(
                        file_bytes,
                        variant_name=input_name,
                        file_type=file_kind,
                        right_of_way_m2=input_row
                    )
                    var.metadata.swelling_factor = input_swelling
                    if var.metadata.total_length_m == 0:
                        var.metadata.total_length_m = input_length

                    add_variant_to_state(var)
                    st.success(f"Variante Civil 3D '{var.name}' importée ({var.metadata.total_length_m:,.0f} m d'axe) !")
                    st.rerun()

            except Exception as e:
                st.error(f"Erreur lors du traitement du fichier : {e}")

    # Aperçu des variantes chargées
    st.divider()
    st.subheader(f"📋 Variantes chargées en mémoire ({len(variants)})")

    if not variants:
        st.info("Aucune variante disponible. Cliquez sur '🚀 Charger Démo' à gauche pour tester immédiatement.")
    else:
        for v_name, v_obj in list(variants.items()):
            with st.expander(f"🛣️ **{v_name}** ({len(v_obj.items)} postes quantitatifs)", expanded=False):
                col_info, col_del = st.columns([5, 1])
                with col_info:
                    render_variant_kpi_cards(v_obj, catalog)
                with col_del:
                    if st.button("🗑️ Supprimer", key=f"del_{v_name}", help="Supprimer cette variante"):
                        remove_variant_from_state(v_name)
                        st.rerun()

                # Table détaillée des postes de la variante
                table_data = [
                    {
                        "Code": it.code,
                        "Désignation": it.designation,
                        "Catégorie": it.category.value,
                        "Quantité": f"{it.quantity:,.2f}",
                        "Unité": it.unit,
                    }
                    for it in v_obj.items.values()
                ]
                st.dataframe(pd.DataFrame(table_data), use_container_width=True)

    # Téléchargement des gabarits vierges
    st.divider()
    st.subheader("📥 Télécharger les modèles vierges (Gabarits)")
    gt1, gt2 = st.columns(2)
    template_dir = Path(__file__).resolve().parent.parent / "data" / "templates"

    with gt1:
        csv_t_var = template_dir / "template_variante_fr.csv"
        if csv_t_var.exists():
            st.download_button(
                "📄 Télécharger Gabarit Variante (.csv)",
                data=csv_t_var.read_bytes(),
                file_name="gabarit_variante_routiere.csv",
                mime="text/csv",
                use_container_width=True
            )
    with gt2:
        csv_t_bpu = template_dir / "template_bpu_prix.csv"
        if csv_t_bpu.exists():
            st.download_button(
                "💰 Télécharger Gabarit BPU Prix (.csv)",
                data=csv_t_bpu.read_bytes(),
                file_name="gabarit_bpu_prix.csv",
                mime="text/csv",
                use_container_width=True
            )


# ------------------------------------------------------------------------------
# ONGLET 2 : BORDEREAU DES PRIX UNITAIRES (BPU)
# ------------------------------------------------------------------------------
with tab_bpu:
    st.subheader("💰 Configuration du Bordereau des Prix Unitaires (BPU)")
    st.write("Ce catalogue applique des prix unitaires réels aux quantités pour estimer le coût des variantes.")

    col_bpu_up, col_bpu_curr = st.columns([3, 1])

    with col_bpu_curr:
        currency = st.selectbox(
            "Devise :",
            options=["EUR", "DZD", "USD", "CAD", "MAD", "CHF"],
            index=0 if catalog is None else ["EUR", "DZD", "USD", "CAD", "MAD", "CHF"].index(catalog.currency) if catalog.currency in ["EUR", "DZD", "USD", "CAD", "MAD", "CHF"] else 0
        )

    with col_bpu_up:
        bpu_file = st.file_uploader(
            "Importer un fichier de prix (CSV / Excel) :",
            type=["csv", "xlsx", "xls"],
            key="bpu_uploader"
        )
        if bpu_file is not None and st.button("📥 Charger ce BPU", type="primary"):
            try:
                b_bytes = io.BytesIO(bpu_file.getvalue())
                is_ex = bpu_file.name.lower().endswith((".xlsx", ".xls"))
                f_type = "excel" if is_ex else "csv"
                new_catalog, rep = parse_cost_catalog(b_bytes, file_type=f_type, currency=currency)
                set_catalog_in_state(new_catalog)
                st.success(f"Catalogue de {len(new_catalog.prices)} prix unitaires chargé avec succès !")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur de lecture du BPU : {e}")

    st.divider()

    # Tableau interactif des prix existants
    if catalog and catalog.prices:
        st.write(f"**Prix unitaires configurés ({len(catalog.prices)} articles en {catalog.currency}) :**")
        bpu_rows = [
            {
                "Code": p.code,
                "Désignation": p.designation,
                "Unité": p.unit,
                f"Prix Unitaire HT ({catalog.currency})": p.price,
            }
            for p in catalog.prices.values()
        ]
        df_bpu = pd.DataFrame(bpu_rows)
        st.dataframe(df_bpu, use_container_width=True)
    else:
        st.warning("⚠️ Aucun bordereau de prix actif. Les calculs de coûts ne seront pas disponibles tant qu'un BPU n'est pas configuré.")


# ------------------------------------------------------------------------------
# ONGLET 3 : COMPARATIF DÉTAILLÉ & MOUVEMENT DES TERRES
# ------------------------------------------------------------------------------
with tab_compare:
    st.subheader("⚖️ Comparaison Multicritère des Variantes")

    if len(variants) < 2:
        st.warning("⚠️ Veuillez charger au moins **2 variantes** pour effectuer une comparaison.")
    else:
        baseline_name = st.session_state.baseline_name
        baseline_variant = variants[baseline_name]

        # Choix de la variante cible à comparer
        eval_candidates = [name for name in variant_names if name != baseline_name]
        target_name = st.selectbox(
            "Sélectionner la variante cible à comparer :",
            options=eval_candidates,
            index=0
        )
        target_variant = variants[target_name]

        # Calcul réel de comparaison
        comparison_res = compare_variants(
            baseline=baseline_variant,
            target=target_variant,
            catalog=catalog
        )

        st.markdown(f"### 🔍 Comparatif : **{target_name}** par rapport à la référence **{baseline_name}**")

        # Rendu des KPIs
        render_comparison_summary_kpis(comparison_res)

        # Graphique Plotly de comparaison des terres
        st.divider()
        st.plotly_chart(
            plot_earthwork_comparison([baseline_variant, target_variant]),
            use_container_width=True
        )

        # Tableau comparatif poste par poste
        st.divider()
        st.subheader("📑 Tableau Comparatif Détaillé Poste par Poste")

        df_comp = format_comparison_dataframe(comparison_res)

        # Filtres interactifs
        f1, f2 = st.columns([1, 2])
        with f1:
            cat_list = ["Toutes les familles"] + sorted(list(df_comp["Famille"].unique()))
            chosen_cat = st.selectbox("Filtrer par famille :", cat_list)
        with f2:
            search_query = st.text_input("🔍 Rechercher un poste (code ou libellé) :", "")

        filtered_df = df_comp.copy()
        if chosen_cat != "Toutes les familles":
            filtered_df = filtered_df[filtered_df["Famille"] == chosen_cat]
        if search_query.strip():
            q = search_query.strip().lower()
            filtered_df = filtered_df[
                filtered_df["Code"].str.lower().str.contains(q) |
                filtered_df["Désignation"].str.lower().str.contains(q)
            ]

        st.dataframe(filtered_df, use_container_width=True, height=360)

        # Exports de la comparaison
        c_exp1, c_exp2, c_exp3 = st.columns(3)
        with c_exp1:
            csv_buffer = filtered_df.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "📥 Exporter tableau filtré (.csv)",
                data=csv_buffer,
                file_name=f"comparatif_{baseline_name}_vs_{target_name}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with c_exp2:
            quick_excel = generate_excel_report(
                comparison=comparison_res,
                baseline_variant=baseline_variant,
                target_variant=target_variant,
                catalog=catalog
            )
            st.download_button(
                "📊 Rapport complet Excel (.xlsx)",
                data=quick_excel,
                file_name=f"rapport_{baseline_name}_vs_{target_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with c_exp3:
            quick_pdf = generate_pdf_report(
                comparison=comparison_res,
                baseline_variant=baseline_variant,
                target_variant=target_variant,
                catalog=catalog
            )
            st.download_button(
                "📄 Rapport officiel PDF (.pdf)",
                data=quick_pdf,
                file_name=f"rapport_{baseline_name}_vs_{target_name}.pdf",
                mime="application/pdf",
                use_container_width=True
            )


# ------------------------------------------------------------------------------
# ONGLET 4 : ANALYSE FINANCIÈRE & DÉCISION
# ------------------------------------------------------------------------------
with tab_finance:
    st.subheader("📊 Analyse Financière et Évaluation Économique")

    if len(variants) < 2:
        st.warning("⚠️ Chargez au moins 2 variantes pour afficher l'analyse financière.")
    elif catalog is None or not catalog.prices:
        st.info("ℹ️ Veuillez configurer un Bordereau des Prix Unitaires (BPU) dans l'Onglet 2 pour débloquer l'analyse financière.")
    else:
        baseline_name = st.session_state.baseline_name
        baseline_variant = variants[baseline_name]
        curr = catalog.currency

        # Calcul des comparaisons pour toutes les autres variantes
        all_comparisons = [
            compare_variants(baseline=baseline_variant, target=variants[name], catalog=catalog)
            for name in variant_names if name != baseline_name
        ]

        b_cost, _, b_missing = calculate_variant_total_cost(baseline_variant, catalog)

        # 1. Graphique général des coûts totaux
        st.plotly_chart(
            plot_total_costs_bar(
                comparisons=all_comparisons,
                baseline_name=baseline_name,
                baseline_cost=b_cost,
                currency=curr
            ),
            use_container_width=True
        )

        # 2. Répartition par famille de travaux et Graphique Tornado
        col_cat_chart, col_tornado = st.columns(2)

        # Sélecteur de variante pour l'analyse détaillée
        selected_for_detail = st.selectbox(
            "Sélectionner la variante pour le détail financier :",
            options=[c.target_name for c in all_comparisons]
        )
        selected_comp = next(c for c in all_comparisons if c.target_name == selected_for_detail)

        with col_cat_chart:
            st.plotly_chart(
                plot_cost_breakdown_by_category(selected_comp, currency=curr),
                use_container_width=True
            )
        with col_tornado:
            st.plotly_chart(
                plot_deltas_tornado(selected_comp),
                use_container_width=True
            )

        # 3. Synthèse de recommandation multicritère
        st.divider()
        st.subheader("💡 Synthèse d'Aide à la Décision")

        ranking_data = []
        for v_name, v_obj in variants.items():
            cost, _, missing_codes = calculate_variant_total_cost(v_obj, catalog)
            bal = calculate_earthwork_balance(v_obj)
            ranking_data.append({
                "Variante": v_name,
                f"Coût Total HT ({curr})": cost,
                "Longueur (m)": v_obj.metadata.total_length_m,
                "Emprise (m²)": v_obj.metadata.right_of_way_m2,
                "Solde Terres (m³)": bal.net_balance_m3,
                "Statut Terres": bal.status.value,
                "Articles sans prix": len(missing_codes),
            })

        df_ranking = pd.DataFrame(ranking_data).sort_values(by=f"Coût Total HT ({curr})")
        st.dataframe(df_ranking, use_container_width=True)

        cheapest_variant = df_ranking.iloc[0]["Variante"]
        cheapest_cost = df_ranking.iloc[0][f"Coût Total HT ({curr})"]
        st.success(
            f"🎯 **Variante économiquement la plus avantageuse :** `{cheapest_variant}` avec une estimation de **{cheapest_cost:,.2f} {curr}** HT."
        )


# ------------------------------------------------------------------------------
# ONGLET 5 : RAPPORTS & EXPORTS (EXCEL / PDF)
# ------------------------------------------------------------------------------
with tab_reports:
    st.subheader("📑 Génération des Rapports Officiels (Excel & PDF)")
    st.write(
        "Générez des rapports certifiés pour présentation aux maîtres d'ouvrages et partenaires, intégrant "
        "l'ensemble des métadonnées, hypothèses, cubatures, coûts, écarts et avertissements techniques."
    )

    if len(variants) < 2:
        st.warning("⚠️ Veuillez charger au moins **2 variantes** pour éditer un rapport comparatif.")
    else:
        baseline_name = st.session_state.baseline_name
        baseline_variant = variants[baseline_name]

        r_col1, r_col2 = st.columns(2)
        with r_col1:
            project_name_input = st.text_input(
                "Nom officiel du projet :",
                value="Projet Routier - Déviation RN",
                key="rep_proj_name"
            )
            author_input = st.text_input(
                "Auteur / Bureau d'études :",
                value="Bureau d'Études VRD & Ouvrages d'Art",
                key="rep_author"
            )
        with r_col2:
            target_candidates = [n for n in variant_names if n != baseline_name]
            target_for_report = st.selectbox(
                "Variante cible à comparer à la référence :",
                options=target_candidates,
                key="report_target_select"
            )
            target_variant = variants[target_for_report]
            include_bpu = st.checkbox(
                "Inclure le volet financier BPU dans le rapport",
                value=catalog is not None and bool(catalog.prices),
                key="rep_inc_bpu"
            )

        active_catalog = catalog if include_bpu else None

        # Calcul effectif
        comp_report = compare_variants(
            baseline=baseline_variant,
            target=target_variant,
            catalog=active_catalog
        )

        # Collecte des avertissements techniques
        report_warnings = []
        if comp_report.target_earthwork.status == EarthworkStatus.DEFICITAIRE:
            report_warnings.append(
                f"Déficit en remblai de {comp_report.target_earthwork.net_balance_m3:,.0f} m³ sur {target_variant.name} : emprunt extérieur requis."
            )
        elif comp_report.target_earthwork.status == EarthworkStatus.EXCEDENTAIRE:
            report_warnings.append(
                f"Excédent de déblais de +{comp_report.target_earthwork.net_balance_m3:,.0f} m³ sur {target_variant.name} : mise en dépôt requise."
            )

        if active_catalog:
            _, _, missing_p = calculate_variant_total_cost(target_variant, active_catalog)
            if missing_p:
                report_warnings.append(
                    f"{len(missing_p)} poste(s) non valorisé(s) dans le BPU : {', '.join(missing_p)}."
                )

        # Affichage du récapitulatif avant génération
        st.info(
            f"📌 **Paramètres du rapport :** Projet `{project_name_input}` | Référence : `{baseline_name}` ({baseline_variant.metadata.total_length_m:,.0f} m) "
            f"| Cible : `{target_for_report}` ({target_variant.metadata.total_length_m:,.0f} m) | Postes : **{len(comp_report.items)}**"
        )

        st.divider()

        # Boutons de téléchargement
        d_col_excel, d_col_pdf = st.columns(2)

        with d_col_excel:
            st.markdown("#### 📊 Rapport Complet Excel (.xlsx)")
            st.caption("Classeur à 3 onglets (Synthèse & Hypothèses, Métré comparatif détaillé, BPU) avec mise en page conditionnelle.")
            excel_bytes = generate_excel_report(
                comparison=comp_report,
                baseline_variant=baseline_variant,
                target_variant=target_variant,
                catalog=active_catalog,
                project_name=project_name_input,
                author=author_input,
                warnings=report_warnings
            )
            st.download_button(
                "📥 Télécharger le Rapport Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"rapport_comparatif_{baseline_name}_vs_{target_for_report}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )

        with d_col_pdf:
            st.markdown("#### 📄 Rapport Officiel PDF (.pdf)")
            st.caption("Document officiel A4 avec cartouche, tableaux comparatifs formatés, avertissements et numérotation dynamique.")
            pdf_bytes = generate_pdf_report(
                comparison=comp_report,
                baseline_variant=baseline_variant,
                target_variant=target_variant,
                catalog=active_catalog,
                project_name=project_name_input,
                author=author_input,
                warnings=report_warnings
            )
            st.download_button(
                "📄 Télécharger le Rapport PDF (.pdf)",
                data=pdf_bytes,
                file_name=f"rapport_comparatif_{baseline_name}_vs_{target_for_report}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )

