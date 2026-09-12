/**
 * « Mes ordres de travail » : uniquement ce qui est en cours.
 *
 * L'onglet accumulait tout ce que l'operateur avait touche. adminWorkorderIds
 * retient un ordre des que l'operateur figure dans employee_assigned_ids — une
 * assignation ne s'efface jamais — ou dans employee_ids, et le filtre d'origine
 * n'ecarte que « cancel », jamais « done » ni « ready » :
 *
 *     const myWorkordersFilter = (wo) =>
 *         this.adminWorkorderIds.includes(wo.resId) && wo.data.state !== "cancel";
 *
 * On reecrit adminWorkorderIds, seul consommateur de ce filtre, en exigeant
 * que l'ordre soit demarre.
 *
 * POURQUOI defineProperty ET PAS patch().
 *
 * Trois versions successives passant par patch() n'ont eu aucun effet en
 * pre-production, et les mesures ont elimine toutes les autres explications :
 * le module est installe, le fichier est sur le disque du build, le bundle
 * web.assets_web.min.js contient nos marqueurs, adminWorkorderIds appartient
 * bien a MrpDisplay (lignes 33 a 694 de mrp_display.js) et aucune sous-classe
 * n'existe dans Enterprise ni dans le coeur.
 *
 * Le seul maillon jamais verifie etait patch() lui-meme. On le contourne :
 * defineProperty pose le getter sur le prototype sans intermediaire, sans
 * super, sans recablage de [[HomeObject]]. C'est exactement ce que faisait la
 * surcharge testee en direct dans la console.
 *
 * LA TRACE. Le console.info en fin de fichier n'est pas un oubli. Savoir si ce
 * fichier s'execute a coute une demi-journee d'allers-retours : la trace rend
 * la reponse immediate, il suffit d'ouvrir la console. A retirer quand le
 * comportement sera stabilise en production.
 *
 * Les onglets par poste de charge passent par workcenterFilter, qui n'utilise
 * pas ce getter : ils restent inchanges. Le compteur de l'en-tete lit le meme
 * getter, il se cale donc sur la liste.
 */
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

console.info("[FMA] Mes ordres de travail : filtre « demarre » actif");
