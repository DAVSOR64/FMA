/**
 * « Mes ordres de travail » : ce sur quoi l'operateur est pointe, maintenant.
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
 * LE CRITERE, ET L'ERREUR QUI A COUTE LA JOURNEE.
 *
 * Les versions precedentes exigeaient state === "progress". Sans effet, et
 * pour une raison qu'aucune de nos mesures ne pouvait montrer : le bouton
 * « DEMARRER » d'une carte ne dit pas que l'ordre n'est pas demarre, il dit
 * que L'OPERATEUR COURANT n'est pas pointe dessus. Un ordre lance plus tot,
 * puis laisse sans chrono actif, reste a l'etat progress. Les cartes etaient
 * donc deja « demarrees » et le filtre ne retirait rien.
 *
 * Le critere demande — « les OT actifs et relies a l'employe sur lequel nous
 * sommes » — n'est pas un etat d'ordre mais un pointage : employee_ids, les
 * operateurs qui ont un chrono en cours. C'est la meme donnee que celle qui
 * fait passer la carte au vert dans mrp_display_record_patch.js.
 *
 * employee_assigned_ids n'est plus consulte : une assignation n'est pas un
 * travail en cours.
 *
 * POURQUOI defineProperty ET PAS patch(). Trois versions passant par patch()
 * n'ont rien change ; on ne saura pas laquelle des deux causes jouait, le
 * critere etant faux de toute facon. defineProperty pose le getter sans
 * intermediaire : une inconnue de moins.
 *
 * LA TRACE. Savoir si ce fichier s'execute a coute une demi-journee. Elle
 * repond en ouvrant la console. A retirer une fois le comportement stabilise.
 *
 * Les onglets par poste de charge passent par workcenterFilter, qui n'utilise
 * pas ce getter : ils restent inchanges. Le compteur de l'en-tete lit le meme
 * getter et se cale donc sur la liste.
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

console.info("[FMA] Mes ordres de travail : pointage de l'operateur courant");
