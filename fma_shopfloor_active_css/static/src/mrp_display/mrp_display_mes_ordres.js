/**
 * « Mes ordres de travail » : uniquement ce qui est en cours.
 *
 * L'onglet accumulait tout l'historique de l'operateur. La cause n'est pas le
 * rattachement a l'employe, mais l'etat retenu :
 *
 *     get adminWorkorderIds() {
 *         const adminId = this.useEmployee.employees.admin.id;
 *         return this.workorders.reduce((idList, wo) =>
 *             wo.data.employee_assigned_ids.resIds.includes(adminId) ||
 *             wo.data.employee_ids.resIds.includes(adminId)
 *                 ? [...idList, wo.resId] : idList, []);
 *     }
 *
 *     const myWorkordersFilter = (wo) =>
 *         this.adminWorkorderIds.includes(wo.resId) && wo.data.state !== "cancel";
 *
 * employee_ids ne contient que les pointes du moment : rien a lui reprocher.
 * C'est employee_assigned_ids qui pollue — une assignation ne s'efface jamais,
 * elle survit a la fin du travail — et le filtre n'ecarte que « cancel », pas
 * « done ». Les ordres TERMINES restaient donc affiches indefiniment.
 *
 * On restreint adminWorkorderIds aux ordres DEMARRES.
 *
 * POURQUOI PAS filteredWorkorders, comme dans la premiere version. Parce que
 * ce getter-la ne suffit qu'a condition de reconnaitre l'onglet actif, via
 * `state.activeWorkcenter === -1`. Or cette valeur transite par le
 * localStorage (_loadActiveWorkcenter) et peut revenir en chaine : une
 * comparaison stricte echoue alors sans bruit, et le filtre ne s'applique a
 * rien. C'est exactement le piege deja rencontre sur le vert.
 *
 * adminWorkorderIds, lui, ne depend d'aucun etat d'onglet : il est consomme
 * par myWorkordersFilter — donc par l'onglet « Mes ordres de travail » et lui
 * seul — et passe en props `adminWorkorders` a l'en-tete, qui affiche le
 * compteur. Le restreindre aligne donc aussi le compteur sur la liste, ce qui
 * etait demande : l'onglet annoncait 3 alors qu'un seul ordre etait demarre.
 *
 * Les onglets par poste de charge passent par workcenterFilter, qui n'utilise
 * pas ce getter : ils restent inchanges.
 */
import { patch } from "@web/core/utils/patch";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

patch(MrpDisplay.prototype, {
    get adminWorkorderIds() {
        const ids = super.adminWorkorderIds;
        if (!ids || !ids.length || !this.workorders) {
            return ids;
        }

        const demarres = new Set();
        for (const wo of this.workorders) {
            if (wo.data.state === "progress") {
                demarres.add(wo.resId);
            }
        }

        return ids.filter((id) => demarres.has(id));
    },
});
