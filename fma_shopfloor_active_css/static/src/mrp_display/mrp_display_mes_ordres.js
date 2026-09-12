/**
 * « Mes ordres de travail » : uniquement ce qui est en cours.
 *
 * L'onglet accumulait tout ce que l'operateur avait touche. La cause n'est pas
 * le rattachement a l'employe : employee_ids ne contient que les pointes du
 * moment. C'est employee_assigned_ids — une assignation ne s'efface jamais,
 * elle survit a la fin du travail — et le filtre d'origine n'ecarte que
 * « cancel », jamais « done » ni « ready » :
 *
 *     const myWorkordersFilter = (wo) =>
 *         this.adminWorkorderIds.includes(wo.resId) && wo.data.state !== "cancel";
 *
 * On reecrit donc adminWorkorderIds, seul consommateur de ce filtre, en y
 * ajoutant la condition d'etat.
 *
 * POURQUOI LE GETTER EST RECOPIE EN ENTIER, SANS super.
 *
 * Les deux versions precedentes appelaient super — sur filteredWorkorders,
 * puis sur adminWorkorderIds — et n'ont eu aucun effet en pre-production. Le
 * code etait pourtant bien servi : le bundle web.assets_web.min.js contient
 * nos trois marqueurs, le module est installe, et aucune sous-classe de
 * MrpDisplay n'existe dans Enterprise.
 *
 * Un getter declare dans un litteral d'objet porte son propre [[HomeObject]] :
 * `super` y designe le prototype du litteral, pas la classe patchee. Selon la
 * facon dont patch() recable ce prototype, l'appel peut renvoyer undefined
 * sans lever — et un getter qui renvoie undefined laisse simplement le filtre
 * d'origine s'appliquer. C'est exactement le symptome observe : aucune erreur,
 * aucun changement.
 *
 * Recopier la dizaine de lignes d'origine coute une relecture a chaque montee
 * de version d'Odoo. C'est le prix a payer pour un comportement certain.
 *
 * Les onglets par poste de charge passent par workcenterFilter, qui n'utilise
 * pas ce getter : ils restent inchanges. Le compteur de l'en-tete, lui, se
 * cale sur la liste — il annoncait 3 quand un seul ordre etait demarre.
 */
import { patch } from "@web/core/utils/patch";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

patch(MrpDisplay.prototype, {
    get adminWorkorderIds() {
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
            // La seule ligne qui nous distingue de l'original.
            if (wo.data.state !== "progress") {
                continue;
            }
            const assignes = (wo.data.employee_assigned_ids || {}).resIds || [];
            const pointes = (wo.data.employee_ids || {}).resIds || [];
            if (assignes.includes(adminId) || pointes.includes(adminId)) {
                retenus.push(wo.resId);
            }
        }
        return retenus;
    },
});
