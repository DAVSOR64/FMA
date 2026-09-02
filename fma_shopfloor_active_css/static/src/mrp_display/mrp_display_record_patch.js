/**
 * Distingue « en cours PAR MOI » de « en cours par quelqu'un d'autre ».
 *
 * Odoo pose la classe `o_active` des que la carte a au moins un operateur
 * pointe dessus, qui que ce soit :
 *
 *     get cssClass() {
 *         const active = this.props.record.data.employee_ids.records.length ? "o_active" : "";
 *         ...
 *     }
 *
 * Un operateur voyait donc en vert les trois OT sur lesquels quelqu'un
 * travaille, alors qu'il n'est que sur un seul. Le CSS seul ne peut pas faire
 * la difference : il ne sait pas qui est connecte.
 *
 * On ajoute `o_fma_mine` quand l'employe de session figure parmi les
 * operateurs pointes. La feuille de style s'appuie ensuite dessus.
 *
 * IDENTIFIER L'EMPLOYE DE SESSION
 *
 * La premiere version lisait `props.sessionOwner`. Sur une tablette partagee,
 * le vert ne fonctionnait alors que pour le PREMIER connecte : cette prop est
 * transmise a la creation de la carte et ne suit pas les changements de
 * session. Quand un second operateur prenait la main, les cartes deja rendues
 * continuaient de comparer a l'identite du premier.
 *
 * On interroge donc plusieurs sources, de la plus vivante a la plus figee, et
 * on prend la premiere qui repond. `props.employees.admin` est celle que le
 * panneau de gauche utilise pour marquer l'operateur connecte : elle suit la
 * session. Aucune n'est garantie d'une version a l'autre, d'ou la cascade.
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

    get cssClass() {
        const classes = super.cssClass;

        const moi = this.fmaEmployeConnecte;
        if (!moi) {
            return classes;
        }

        const pointes = this.props.record.data.employee_ids;
        const records = (pointes && pointes.records) || [];
        const cestMoi = records.some(
            (employe) => (employe.resId || (employe.data && employe.data.id)) === moi
        );

        return cestMoi ? `${classes} o_fma_mine` : classes;
    },
});
