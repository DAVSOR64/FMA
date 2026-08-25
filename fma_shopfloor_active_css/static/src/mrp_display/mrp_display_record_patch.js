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
 * travaille, alors qu'il n'est que sur un seul. Le CSS seul ne peut pas
 * faire la difference : il ne sait pas qui est connecte.
 *
 * On ajoute `o_fma_mine` quand l'employe de session — celui que le panneau
 * de gauche marque `o_admin_user` — figure parmi les operateurs pointes.
 * La feuille de style s'appuie ensuite dessus.
 */
import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

patch(MrpDisplayRecord.prototype, {
    get cssClass() {
        const classes = super.cssClass;

        // sessionOwner vaut {} tant qu'aucun operateur n'a pris la session.
        const moi = this.props.sessionOwner && this.props.sessionOwner.id;
        if (!moi) {
            return classes;
        }

        const pointes = this.props.record.data.employee_ids;
        const records = (pointes && pointes.records) || [];
        const cestMoi = records.some(
            (employe) => (employe.resId || employe.data.id) === moi
        );

        return cestMoi ? `${classes} o_fma_mine` : classes;
    },
});
