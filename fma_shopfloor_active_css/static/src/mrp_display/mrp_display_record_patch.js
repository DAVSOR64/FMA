/**
 * Distingue « en cours PAR MOI » de « en cours par quelqu'un d'autre ».
 *
 * Odoo pose la classe `o_active` des que la carte a au moins un operateur
 * pointe dessus, qui que ce soit. Un operateur voyait donc en vert tous les
 * ordres sur lesquels quelqu'un travaille, alors qu'il n'est que sur un seul.
 * Le CSS seul ne peut pas faire la difference : il ne sait pas qui est
 * connecte. On ajoute donc `o_fma_mine`, sur laquelle la feuille de style
 * s'appuie.
 *
 * Deux pieges rencontres en pre-production, tous deux corriges ci-dessous.
 *
 * QUI EST CONNECTE. `props.sessionOwner` est transmise a la creation de la
 * carte et ne suit pas les changements de session : le vert restait colle au
 * premier connecte. On interroge plusieurs sources, de la plus vivante a la
 * plus figee. `props.employees.admin` vient en tete : c'est celle que le
 * panneau de gauche utilise pour marquer l'operateur connecte.
 *
 * QUI POINTE. `employee_ids.records` ne contient que les enregistrements
 * REELLEMENT charges par le client, souvent le dernier seul. Quand deux
 * operateurs pointaient sur le meme ordre, seul le SECOND voyait sa carte en
 * vert : le premier n'etait pas dans la liste comparee. `currentIds` et
 * `resIds` portent, eux, la totalite des identifiants.
 */
import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

patch(MrpDisplayRecord.prototype, {
    get fmaEmployeConnecte() {
        const p = this.props || {};
        const candidats = [
            p.employees && p.employees.admin && p.employees.admin.id,
            p.sessionOwner && p.sessionOwner.id,
            p.production && p.production.employees
                && p.production.employees.admin && p.production.employees.admin.id,
        ];
        for (const id of candidats) {
            if (id) {
                return id;
            }
        }
        return false;
    },

    get fmaOperateursPointes() {
        const champ = this.props.record.data.employee_ids;
        if (!champ) {
            return [];
        }
        for (const source of [champ.currentIds, champ.resIds]) {
            if (source && source.length !== undefined) {
                return Array.from(source);
            }
        }
        const records = champ.records || [];
        return records.map((e) => e.resId || (e.data && e.data.id));
    },

    get cssClass() {
        const classes = super.cssClass;

        const moi = this.fmaEmployeConnecte;
        if (!moi) {
            return classes;
        }

        // Comparaison souple : selon la source, un identifiant peut arriver
        // en nombre ou en chaine. Une egalite stricte echouerait en silence.
        const pointes = this.fmaOperateursPointes;
        const cestMoi = pointes.some((id) => Number(id) === Number(moi));

        return cestMoi ? `${classes} o_fma_mine` : classes;
    },
});
