# -*- coding: utf-8 -*-
"""Point d'entree commercial de la mise en lot.

Le devis est l'ecran d'ou part le lotissement : un bouton ouvre le wizard
qui liste les lignes et laisse saisir, pour chacune, un numero de lot et la
quantite a y placer.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    lot_ids = fields.Many2many(
        "fma.lot.fabrication",
        string="Lots de fabrication",
        compute="_compute_lot_ids",
        store=False,
    )
    lot_count = fields.Integer(
        string="Nb lots",
        compute="_compute_lot_ids",
    )
    qty_to_lot_total = fields.Float(
        string="Reste a lotir",
        compute="_compute_lot_ids",
        digits="Product Unit of Measure",
    )

    @api.depends(
        "order_line.lot_line_ids.lot_id",
        "order_line.lot_line_ids.lot_id.state",
        "order_line.lot_line_ids.product_qty",
        "order_line.product_uom_qty",
        "order_line.is_lotable",
    )
    def _compute_lot_ids(self):
        for order in self:
            lot_lines = order.order_line.lot_line_ids.filtered(
                lambda l: l.lot_id.state != "cancel"
            )
            order.lot_ids = lot_lines.mapped("lot_id")
            order.lot_count = len(order.lot_ids)
            order.qty_to_lot_total = sum(
                order.order_line.filtered("is_lotable").mapped("qty_to_lot")
            )

    # ------------------------------------------------------------------
    # Couplage lots <-> OF standards
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Confirme la commande, puis rattache les OF natifs aux lots.

        La generation des OF reste **standard** : c'est l'approvisionnement
        Odoo qui les cree a la confirmation, ce qui declenche les besoins
        composants et relie l'OF a la livraison. Mais le natif raisonne par
        ligne de commande, alors que l'atelier fabrique par lot : on scinde
        donc chaque OF selon la repartition du lotissement.
        """
        res = super().action_confirm()
        self._dispatch_productions_to_lots()
        return res

    def _dispatch_productions_to_lots(self):
        """Scinde les OF issus de l'appro et les affecte a leur lot."""
        Production = self.env["mrp.production"]
        for order in self:
            for line in order.order_line:
                allocations = line.lot_line_ids.filtered(
                    lambda a: not a.production_id and a.product_qty > 0
                ).sorted(lambda a: (a.lot_id.name or "", a.id))
                if not allocations:
                    continue

                productions = Production.search(
                    [
                        ("sale_line_id", "=", line.id),
                        ("state", "not in", ("done", "cancel")),
                        ("lot_fabrication_id", "=", False),
                    ]
                )
                if len(productions) != 1:
                    # Aucun OF natif, ou plusieurs : on ne devine pas. Le
                    # bouton du lot reste disponible pour completer.
                    continue

                self._assign_production_to_lots(productions, allocations)

    def _assign_production_to_lots(self, production, allocations):
        """Scinde un OF selon les quantites des lots, puis les rattache."""
        amounts = [alloc.product_qty for alloc in allocations]
        reste = production.product_qty - sum(amounts)
        if float_compare(reste, 0.0, precision_digits=2) > 0:
            # Une part de la ligne n'est pas lotie : elle reste sur un OF
            # a part, que le natif continue de piloter.
            amounts.append(reste)
        elif float_compare(reste, 0.0, precision_digits=2) < 0:
            # Plus de quantite lotie que produite : le lotissement a change
            # apres coup. On ne scinde pas, on laisse l'ecart visible.
            return

        productions = production
        if len(amounts) > 1:
            productions = production._split_productions({production: amounts})

        for alloc, split in zip(allocations, productions):
            vals = {
                "lot_fabrication_id": alloc.lot_id.id,
                "lot_line_id": alloc.id,
                "lot_sale_line_id": alloc.sale_line_id.id,
                "lot_production_type": "assemblage",
            }
            # Le chantier, repris depuis la commande. Ces OF viennent de
            # l'appro natif et ne passent pas par le lot : sans cette ligne,
            # ils sortaient sans projet. Champ declare par « custom », dont ce
            # module ne depend pas — d'ou le controle.
            projet = alloc.sale_line_id.order_id.project_id
            if projet and "x_studio_projet_de_la_vente" in split._fields:
                vals["x_studio_projet_de_la_vente"] = projet.id
            split.write(vals)
            alloc.production_id = split
            split._add_debit_component(
                alloc.lot_id._get_product_debit(), alloc.product_qty
            )

    def action_open_lot_wizard(self):
        """Ouvre le wizard de mise en lot pour cette commande."""
        self.ensure_one()
        if self.state in ("cancel",):
            raise UserError(
                _("La commande %s est annulee.", self.display_name)
            )
        lines = self.order_line.filtered("is_lotable")
        if not lines:
            raise UserError(
                _(
                    "La commande %s ne contient aucune ligne a lotir "
                    "(articles stockables ou consommables).",
                    self.display_name,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Mise en lot - %s", self.name),
            "res_model": "fma.lot.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def action_view_lots(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "fma_lot_fabrication.action_fma_lot_fabrication"
        )
        lots = self.lot_ids
        action["domain"] = [("id", "in", lots.ids)]
        if len(lots) == 1:
            action["views"] = [
                (
                    self.env.ref(
                        "fma_lot_fabrication.view_fma_lot_fabrication_form"
                    ).id,
                    "form",
                )
            ]
            action["res_id"] = lots.id
        return action
