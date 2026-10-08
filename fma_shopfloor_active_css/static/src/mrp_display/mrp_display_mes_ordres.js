/**
 * « Mes ordres de travail » : ce sur quoi l'operateur est pointe, ou qu'il soit.
 *
 * Deux corrections successives sur le meme ecran, et une troisieme qui revient
 * sur la deuxieme.
 *
 * ---------------------------------------------------------------------------
 * 1. LE CRITERE : pointage, pas assignation.
 *
 * Le getter d'origine retient un ordre des que l'operateur figure dans
 * employee_assigned_ids OU dans employee_ids, et le filtre qui le consomme
 * n'ecarte que « cancel » :
 *
 *     const myWorkordersFilter = (wo) =>
 *         this.adminWorkorderIds.includes(wo.resId) && wo.data.state !== "cancel";
 *
 * employee_assigned_ids est le coupable : une assignation ne s'efface jamais.
 * L'operateur retrouvait donc dans son onglet tout ce qui lui avait ete
 * attribue, termine ou non.
 *
 * Le piege, qui a coute une journee : exiger state === "progress" ne changeait
 * rien. Le bouton « DEMARRER » d'une carte ne dit pas que l'ordre n'est pas
 * demarre, il dit que L'OPERATEUR COURANT n'est pas pointe dessus. Un ordre
 * lance plus tot, puis laisse sans chrono actif, reste a l'etat progress.
 *
 * Le critere demande — « les OT actifs et relies a l'employe sur lequel nous
 * sommes » — n'est pas un etat d'ordre mais un pointage : employee_ids, les
 * operateurs qui ont un chrono en cours.
 *
 * ---------------------------------------------------------------------------
 * 2. LA PAGINATION : le filtre ne voyait qu'une page.
 *
 * L'ecran pagine les ordres de FABRICATION — 40 sur 214 — et les ordres de
 * travail en decoulent :
 *
 *     get workorders() {
 *         return this.model.root.records.flatMap((mo) => mo.data.workorder_ids.records);
 *     }
 *
 * Tous les onglets filtrent donc cette page-la. Sur une meme session : page
 * 81-120, « Mes ordres de travail 0 », « Debit FMA 22 » ; page 41-80, « Mes
 * ordres de travail 1 », « Debit FMA 35 ».
 *
 * ---------------------------------------------------------------------------
 * 3. ET POURQUOI ON NE CHARGE PAS TOUT.
 *
 * La premiere reponse a ete d'appeler setMaxLimit(), le natif derriere
 * « Charger tous les ordres de fabrication ». Correct, et inutilisable : 214
 * ordres de fabrication avec leurs mouvements, leurs controles qualite et
 * leurs lots, l'atelier attendait.
 *
 * Le bon geste n'est pas de tout charger pour en garder trois, c'est de ne
 * demander que ce qu'on garde. L'onglet pose donc un DOMAINE, et le serveur
 * ne renvoie que les ordres de fabrication concernes :
 *
 *   - « Mes ordres de travail » : workorder_ids.employee_ids contient
 *     l'operateur connecte — les rares OF ou il a un chrono en cours ;
 *   - un poste de charge : workorder_ids.workcenter_id vaut ce poste.
 *
 * La pagination redevient alors sans objet : il n'y a plus rien a paginer.
 * Et les compteurs deviennent justes, puisqu'ils comptent sur un ensemble
 * complet — c'est le meme defaut qui donnait 22 ordres au Debit au lieu de 35.
 *
 * La vue d'ensemble est laissee telle quelle : elle liste les ordres de
 * fabrication eux-memes, et la pagination y a un sens.
 *
 * On surveille le couple (onglet, operateur connecte) plutot que le seul clic
 * sur l'onglet : quand un autre operateur prend la main sur la tablette, son
 * onglet doit suivre sans qu'il ait a le re-selectionner.
 */
import { patch } from "@web/core/utils/patch";
import { onWillRender } from "@odoo/owl";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

Object.defineProperty(MrpDisplay.prototype, "adminWorkorderIds", {
    configurable: true,
    get() {
        const admin =
            this.useEmployee &&
            this.useEmployee.employees &&
            this.useEmployee.employees.admin;
        const adminId = admin && admin.id;
        if (!adminId || !this.workorders) {
            return [];
        }

        const retenus = [];
        for (const wo of this.workorders) {
            // employee_ids : les operateurs qui ont un chrono en cours sur cet
            // ordre. Un ordre pointe est actif par definition — inutile de
            // verifier l'etat en plus.
            const pointes = (wo.data.employee_ids || {}).resIds || [];
            if (pointes.includes(adminId)) {
                retenus.push(wo.resId);
            }
        }
        return retenus;
    },
});

patch(MrpDisplay.prototype, {
    setup() {
        super.setup();
        // Le filtre serveur deja applique, et un verrou : un chargement en
        // cours ne doit pas en declencher un second au rendu suivant.
        this.fmaFiltreApplique = null;
        this.fmaChargementEnCours = false;
        onWillRender(() => this.fmaSurveillerOnglet());
    },

    get fmaOperateurConnecte() {
        const admin =
            this.useEmployee &&
            this.useEmployee.employees &&
            this.useEmployee.employees.admin;
        return (admin && admin.id) || false;
    },

    /**
     * Le domaine a demander au serveur pour l'onglet courant.
     *
     * On repart du domaine de l'ecran — celui que la barre de recherche et les
     * postes actives composent — et on y ajoute une seule condition. Le
     * remplacer ferait disparaitre la recherche que l'operateur vient de
     * taper.
     */
    get fmaDomaineOnglet() {
        const base = (this.env.searchModel && this.env.searchModel.domain) || [];
        const onglet = Number(this.state.activeWorkcenter);
        if (!onglet) {
            return base; // vue d'ensemble : les OF eux-memes
        }
        if (onglet === -1) {
            const operateur = this.fmaOperateurConnecte;
            return operateur
                ? [...base, ["workorder_ids.employee_ids", "in", [operateur]]]
                : base;
        }
        return [...base, ["workorder_ids.workcenter_id", "=", onglet]];
    },

    fmaSurveillerOnglet() {
        const onglet = Number(this.state.activeWorkcenter);
        const cle = `${onglet}:${onglet === -1 ? this.fmaOperateurConnecte : 0}`;
        if (cle === this.fmaFiltreApplique || this.fmaChargementEnCours) {
            return;
        }
        this.fmaFiltreApplique = cle;
        this.fmaChargementEnCours = true;
        // Hors du rendu : charger pendant qu'OWL rend ferait boucler.
        Promise.resolve().then(async () => {
            try {
                await this.fmaChargerOnglet();
            } catch (erreur) {
                // Le filtre serveur est un confort. S'il echoue, l'ecran
                // retombe sur son comportement d'origine — page courante
                // filtree cote client — plutot que de rester blanc.
                this.fmaFiltreApplique = null;
                console.warn("[FMA] filtre d'onglet non applique", erreur);
            } finally {
                this.fmaChargementEnCours = false;
            }
        });
    },

    async fmaChargerOnglet() {
        this.invalidateRecordIdsCache();
        this.state.offset = 0;
        await this.model.load({ domain: this.fmaDomaineOnglet, offset: 0 });
    },
});
