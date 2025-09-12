from odoo import models

class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _report_locations_for_product(self, product):
        """Retourne la liste des emplacements internes où le produit a du stock,
           en EXCLUANT toute ligne dont le nom contient 'Pré-fabrication'."""
        Quant = self.env["stock.quant"]
        quants = Quant.read_group(
            domain=[
                ("product_id", "=", product.id),
                ("quantity", ">", 0),
                ("location_id.usage", "=", "internal"),
            ],
            fields=["quantity:sum", "location_id"],
            groupby=["location_id"],
            lazy=False,
        )

        res = []
        for q in quants:
            name = q["location_id"][1] if q.get("location_id") else ""
            # ➜ masque REM/Pré-fabrication, LRE/Pré-fabrication, etc.
            if "pré-fabrication" in name.lower():
                continue
            res.append({"name": name, "qty": q.get("quantity", 0)})

        res.sort(key=lambda x: (-x["qty"], x["name"]))
        return res
