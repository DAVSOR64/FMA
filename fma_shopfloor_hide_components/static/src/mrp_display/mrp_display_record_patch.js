import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

patch(MrpDisplayRecord.prototype, {
    get moves() {
        return [];
    },

    get byProducts() {
        return [];
    },
});
