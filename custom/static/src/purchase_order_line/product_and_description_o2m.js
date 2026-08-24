/**
 * Lignes de commande d'achat : « Produit » et « Description » côte à côte.
 *
 * Le widget standard `product_label_section_and_note_field_o2m` fusionne les
 * deux colonnes. Dès que « Produit » est affichée, le rendu de liste retire la
 * colonne « Description » (product/static/src/product_name_and_description/
 * product_name_and_description.js, ProductNameAndDescriptionListRendererMixin.
 * getActiveColumns) et réaffiche le texte sous le nom du produit, dans la même
 * cellule. Ce texte est en plus amputé du nom du produit (`get label()`) : sur
 * une ligne dont la description est identique au produit -- le cas courant --
 * il ne reste donc rien à afficher, et la description semble avoir disparu.
 *
 * Ce widget rétablit les deux colonnes distinctes, même quand elles portent la
 * même valeur. Il est volontairement enregistré sous un nom propre et posé
 * uniquement sur les lignes d'achat (views/purchase_order_views.xml) : le
 * widget d'origine est partagé avec les factures et avoirs fournisseurs
 * (account.move), qui conservent le comportement standard.
 */
import { registry } from "@web/core/registry";
import {
    ProductLabelSectionAndNoteListRender,
    ProductLabelSectionAndNoteOne2Many,
    productLabelSectionAndNoteOne2Many,
} from "@account/components/product_label_section_and_note_field/product_label_section_and_note_field_o2m";

export class ProductAndDescriptionListRenderer extends ProductLabelSectionAndNoteListRender {
    /**
     * @override
     */
    getActiveColumns() {
        const activeColumns = super.getActiveColumns();
        const descriptionColumn = this.allColumns.find(
            (col) => col.name === this.descriptionColumn
        );
        if (!descriptionColumn || activeColumns.includes(descriptionColumn)) {
            // Colonne intacte : « Produit » est masquée, rien n'a été fusionné.
            return activeColumns;
        }
        if (!this.isColumnEnabled(descriptionColumn)) {
            // L'utilisateur a décoché « Description » : on ne la force pas.
            return activeColumns;
        }
        // La description a de nouveau sa propre colonne : ne pas la dupliquer
        // sous le nom du produit.
        this.props.list.records.forEach((record) => (record.columnIsProductAndLabel = false));
        const keptColumns = new Set(activeColumns);
        // Filtrer allColumns (plutôt qu'insérer) préserve l'ordre de la vue.
        return this.allColumns.filter(
            (col) => keptColumns.has(col) || col === descriptionColumn
        );
    }

    /**
     * Même règle que ListRenderer.getActiveColumns, appliquée à une colonne.
     */
    isColumnEnabled(column) {
        if (column.optional && !this.optionalActiveFields[column.name]) {
            return false;
        }
        return !this.evalColumnInvisible(column.column_invisible);
    }
}

export class ProductAndDescriptionOne2Many extends ProductLabelSectionAndNoteOne2Many {
    static components = {
        ...super.components,
        ListRenderer: ProductAndDescriptionListRenderer,
    };
}

export const productAndDescriptionOne2Many = {
    ...productLabelSectionAndNoteOne2Many,
    component: ProductAndDescriptionOne2Many,
};

registry.category("fields").add("fma_product_and_description_o2m", productAndDescriptionOne2Many);
