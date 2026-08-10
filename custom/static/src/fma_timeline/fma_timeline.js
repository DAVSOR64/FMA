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
 */
const ETAPES = [
    ["so_date_de_reception_devis", "Demande reçue"],
    ["so_date_du_devis", "Devis fait"],
    ["so_date_devis_valide", "Devis validé"],
    ["so_date_ARC", "ARC"],
    ["so_date_bpe", "BPE"],
    ["so_date_bon_pour_fab", "Bon pour fab."],
    ["so_date_de_fin_de_production_reel", "Fin de production"],
    ["so_date_de_livraison", "Livraison"],
];

export class FmaTimeline extends Component {
    static template = "custom.FmaTimeline";
    static props = { ...standardWidgetProps };

    get etapes() {
        const donnees = this.props.record.data;
        return ETAPES.map(([champ, libelle]) => {
            const valeur = donnees[champ];
            return {
                libelle,
                date: valeur ? formatDate(valeur) : "",
                faite: Boolean(valeur),
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
