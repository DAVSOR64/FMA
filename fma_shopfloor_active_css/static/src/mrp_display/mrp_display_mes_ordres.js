/**
 * « Mes ordres de travail » : ce sur quoi l'operateur est pointe, ou qu'il soit.
 *
 * Deux corrections, posees a un an d'intervalle sur le meme ecran.
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
 * operateurs qui ont un chrono en cours. C'est la meme donnee que celle qui
 * fait passer la carte au vert dans mrp_display_record_patch.js.
 *
 * defineProperty plutot que patch() : trois versions passant par patch()
 * n'avaient rien change, on ne saura pas laquelle des deux causes jouait.
 * defineProperty pose le getter sans intermediaire, une inconnue de moins.
 *
 * ---------------------------------------------------------------------------
 * 2. LA PAGINATION : le filtre ne voyait qu'une page.
 *
 * L'ecran pagine les ORDRES DE FABRICATION — 40 sur 214 — et les ordres de
 * travail en decoulent :
 *
 *     get workorders() {
 *         return this.model.root.records.flatMap((mo) => mo.data.workorder_ids.records);
 *     }
 *
 * Tous les onglets filtrent donc cette page-la, et rien d'autre. Sur une meme
 * session : page 81-120, « Mes ordres de travail 0 », « Debit FMA 22 » ; page
 * 41-80, « Mes ordres de travail 1 », « Debit FMA 35 ». L'operateur devait
 * parcourir les pages une a une pour tomber sur son ordre.
 *
 * Aucun filtre cote client ne peut corriger cela : ce qui manque n'est pas
 * filtre, il n'est pas charge. On agit donc sur le chargement.
 *
 * setMaxLimit() est natif — c'est ce que fait le bouton « Charger tous les
 * ordres de fabrication » de la vue d'ensemble. On l'appelle des qu'un onglet
 * d'ordres de travail est choisi, ce qui vaut aussi pour les postes de charge :
 * voir 22 ordres sur 35 au Debit est faux de la meme facon.
 *
 * La vue d'ensemble est laissee telle quelle : elle liste les ordres de
 * fabrication eux-memes, et la pagination y a un sens.
 *
 * Le cout est paye UNE fois. setMaxLimit ecrit la limite dans l'etat : les
 * rechargements suivants restent complets, et seul le bouton « Rafraichir » la
 * ramene a la valeur de l'action.
 */
import { patch } from "@web/core/utils/patch";
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
    async selectWorkcenter(workcenterId, showcaseId = false) {
        await super.selectWorkcenter(workcenterId, showcaseId);

        // 0 = vue d'ensemble : on y liste les ordres de fabrication, la
        // pagination garde son sens. Tout le reste affiche des ordres de
        // travail, qui doivent etre complets.
        if (!Number(workcenterId)) {
            return;
        }
        const racine = this.model && this.model.root;
        if (racine && racine.count > racine.records.length) {
            await this.setMaxLimit();
        }
    },
});
