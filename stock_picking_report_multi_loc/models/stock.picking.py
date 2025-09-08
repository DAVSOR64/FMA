from odoo import models

class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _report_locations_for_product(self, product):
        """Tous les emplacements internes où le produit a du stock > 0."""
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
            res.append({"name": name, "qty": q.get("quantity", 0)})
        res.sort(key=lambda x: (-x["qty"], x["name"]))
        return res
