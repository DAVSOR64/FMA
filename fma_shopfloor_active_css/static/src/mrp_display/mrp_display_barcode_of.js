/**
 * Scanner un OF qui n'est pas affiche a l'ecran.
 *
 * L'Atelier sait deja ouvrir un ordre scanne par son nom, mais il le cherche
 * dans `this.productions`, c'est-a-dire `this.model.root.records` : les
 * ordres DEJA CHARGES. Deux situations courantes les en excluent :
 *
 *  - un filtre est actif — « OF pret » laisse de cote les ordres confirmes ;
 *  - la liste est paginee — 40 ordres charges sur 81, et l'atelier en a bien
 *    plus sur un poste charge.
 *
 * Dans ces cas le scan ne trouvait rien et retombait sur la recherche d'un
 * composant, qui echoue a son tour SANS RIEN DIRE. L'operateur scanne, rien
 * ne bouge, et il en conclut que la douchette est cassee.
 *
 * On interroge donc le serveur quand l'ecran ne connait pas le code, et on
 * passe la main a la methode d'origine des qu'un ordre porte ce nom : la
 * suite — la facette de recherche — reste celle d'Odoo, pour qu'un scan se
 * comporte pareil que l'ordre soit charge ou non.
 */
import { patch } from "@web/core/utils/patch";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

patch(MrpDisplay.prototype, {
    async _onBarcodeScanned(barcode) {
        // Les memes gardes que la methode d'origine : les codes internes
        // d'Odoo et les scans destines a une boite de dialogue ouverte ne
        // nous concernent pas.
        const reserve =
            barcode.startsWith("OBT") ||
            barcode.startsWith("OCD") ||
            Object.values(this.overlayService.overlays).find(
                (o) => o.component.name === "DialogWrapper"
            );
        if (!reserve && !this.productions.some((mo) => mo.data.name === barcode)) {
            const trouves = await this.orm.search(
                "mrp.production",
                [["name", "=", barcode]],
                { limit: 1 }
            );
            if (trouves.length) {
                return this._onProductionBarcodeScanned(barcode);
            }
        }
        return super._onBarcodeScanned(barcode);
    },
});
