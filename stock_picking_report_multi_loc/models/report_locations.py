from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _report_locations_for_product(self, product):
        """Retourne la liste des emplacements internes où le produit a du stock,
        en EXCLUANT toute ligne dont le nom contient 'Pré-fabrication'."""
        Quant = self.env["stock.quant"]
        quants = Quant._read_group(
            domain=[
                ("product_id", "=", product.id),
                ("quantity", ">", 0),
                ("location_id.usage", "=", "internal"),
            ],
            groupby=["location_id"],
            aggregates=["quantity:sum"],
        )

        res = []
        for (location, qty_sum) in quants:
            name = location.display_name if location else ""
            # ➜ masque REM/Pré-fabrication, LRE/Pré-fabrication, etc.
            if "pré-fabrication" in name.lower():
                continue
            res.append({"name": name, "qty": qty_sum or 0})

        res.sort(key=lambda x: (-x["qty"], x["name"]))
        return res
