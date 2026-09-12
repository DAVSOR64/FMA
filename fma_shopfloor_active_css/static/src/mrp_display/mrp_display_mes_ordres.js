/**
 * « Mes ordres de travail » : uniquement ce qui est en cours.
 *
 * L'onglet accumulait tout l'historique de l'operateur. La cause n'est pas
 * celle qu'on imagine : elle n'est pas dans le rattachement a l'employe, mais
 * dans l'etat retenu.
 *
 * adminWorkorderIds retient un ordre quand l'operateur figure dans
 * employee_ids — les pointes du moment — OU dans employee_assigned_ids. Or une
 * assignation ne s'efface jamais : elle survit a la fin du travail. Et le
 * filtre d'origine n'ecarte que « cancel » :
 *
 *     const myWorkordersFilter = (wo) =>
 *         this.adminWorkorderIds.includes(wo.resId) && wo.data.state !== "cancel";
 *
 * Les ordres TERMINES restaient donc affiches, indefiniment. Un operateur de
 * plusieurs mois d'anciennete finissait avec une liste illisible, et perdait
 * de vue les deux ou trois cartes qui le concernaient vraiment.
 *
 * On ajoute la seule condition qui manquait : l'ordre doit etre demarre.
 *
 * POURQUOI ICI ET PAS SUR adminWorkorderIds. Ce getter est aussi passe en
 * props dans mrp_display.xml (adminWorkorders) : le restreindre changerait
 * aussi ce qui s'appuie dessus ailleurs. filteredWorkorders, lui, n'a qu'un
 * seul consommateur — defineRelevantRecords — et la garde sur
 * activeWorkcenter === -1 limite l'effet au seul onglet « Mes ordres de
 * travail ». Les onglets par poste de charge ne bougent pas d'un pixel.
 */
import { patch } from "@web/core/utils/patch";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

patch(MrpDisplay.prototype, {
    get filteredWorkorders() {
        const ordres = super.filteredWorkorders;

        // -1 est l'onglet « Mes ordres de travail ». Tout autre valeur est un
        // poste de charge, filtre par workcenterFilter : on n'y touche pas.
        if (this.state.activeWorkcenter !== -1) {
            return ordres;
        }

        return ordres.filter((wo) => wo.data.state === "progress");
    },
});
