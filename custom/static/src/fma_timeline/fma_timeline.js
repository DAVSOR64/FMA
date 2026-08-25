/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { formatDate } from "@web/core/l10n/dates";

/**
 * Frise de suivi d'une affaire, en lecture seule.
 *
 * Les dates restent modifiables dans l'onglet Chronologie, qui en est la
 * source de verite : la frise n'en est que la representation.
 *
 * Chaque etape porte la teinte de sa phase : bleu pour le devis, vert pour
 * la commande, orange pour la production et la livraison. Ce sont les
 * couleurs des libelles de dates de la fiche (classes label-blue,
 * label-green et label-orange) — la frise reprend le meme code, sans quoi
 * elle raconterait l'avancement dans un langage different du reste du devis.
 */
const ETAPES = [
    ["so_date_de_reception_devis", "Demande reçue", "bleu"],
    ["so_date_du_devis", "Devis fait", "bleu"],
    ["so_date_devis_valide", "Devis validé", "bleu"],
    ["so_date_ARC", "ARC", "vert"],
    ["so_date_bpe", "BPE", "vert"],
    ["so_date_bon_pour_fab", "Bon pour fab.", "orange"],
    ["so_date_de_fin_de_production_reel", "Fin de production", "orange"],
    ["so_date_de_livraison", "Livraison", "orange"],
];

export class FmaTimeline extends Component {
    static template = "custom.FmaTimeline";
    static props = { ...standardWidgetProps };

    get etapes() {
        const donnees = this.props.record.data;
        // La premiere etape non franchie est l'etape en cours : sur une frise
        // en fleche, c'est elle qui dit ou en est l'affaire. Sans ce repere,
        // toutes les etapes a venir se ressemblent.
        let encoursPose = false;
        return ETAPES.map(([champ, libelle, teinte]) => {
            const valeur = donnees[champ];
            const faite = Boolean(valeur);
            const date = faite ? formatDate(valeur) : "";
            const encours = !faite && !encoursPose;
            if (encours) {
                encoursPose = true;
            }
            let etat = "";
            if (faite) {
                etat = "fma_timeline_faite";
            } else if (encours) {
                etat = "fma_timeline_encours";
            }
            return {
                libelle,
                date: date || "\u2014",
                classe: `fma_timeline_${teinte} ${etat}`.trim(),
                // Le libelle est tronque quand la fiche est etroite : l'info
                // reste accessible au survol.
                titre: faite ? `${libelle} : ${date}` : `${libelle} : a venir`,
            };
        });
    }
}

registry.category("view_widgets").add("fma_timeline", {
    component: FmaTimeline,
    // Sans cela, les dates ne seraient pas chargees par la vue : le widget
    // n'affiche aucun champ, il ne fait que les lire.
    fieldDependencies: ETAPES.map(([name]) => ({ name, type: "date" })),
});
