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
 *
 * ---------------------------------------------------------------------------
 * ET L'ETIQUETTE D'UNE MENUISERIE.
 *
 * L'Atelier ne sait chercher qu'un NUMERO D'ORDRE. L'etiquette d'une
 * menuiserie porte, elle, son NUMERO DE SERIE : c'est la menuiserie que
 * l'etiquette designe, pas le document qui la fabrique. Scannee ici, elle ne
 * trouvait donc rien — alors que l'etiquette de DEBIT, qui n'a pas de numero
 * de serie et porte celui de son ordre, marchait. D'ou l'impression qu'une
 * des deux etiquettes seulement etait lisible.
 *
 * Le serveur sait relier les deux : fma_ordre_du_code accepte le numero de
 * serie, le lien du QR code et le numero d'ordre, et rend le nom de l'ordre
 * a ouvrir. On ne l'appelle qu'en dernier, quand aucun ordre ne porte ce
 * nom, et un echec laisse le scan suivre son chemin d'origine : devant un
 * operateur, un code mal lu ne doit pas lever une fenetre d'erreur.
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
            let ordre = "";
            try {
                ordre = await this.orm.call(
                    "mrp.production",
                    "fma_ordre_du_code",
                    [barcode]
                );
            } catch {
                ordre = "";
            }
            if (ordre) {
                return this._onProductionBarcodeScanned(ordre);
            }
        }
        return super._onBarcodeScanned(barcode);
    },
});
