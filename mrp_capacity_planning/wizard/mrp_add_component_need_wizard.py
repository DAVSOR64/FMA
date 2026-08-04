# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpAddComponentNeedWizard(models.TransientModel):
    _name = "mrp.add.component.need.wizard"
    _description = "Ajouter un besoin composant sur un OF"
    _auto = True

    production_id = fields.Many2one(
        "mrp.production",
        string="Ordre de fabrication",
        required=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Article à ajouter",
        required=True,
        domain="[('type', 'in', ['product', 'consu'])]",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unité",
        required=True,
    )
    product_qty = fields.Float(
        string="Quantité",
        required=True,
        default=1.0,
    )
    date_planned = fields.Datetime(
        string="Date souhaitée",
        default=fields.Datetime.now,
        help="Date souhaitée pour la disponibilité du besoin. Elle sera portée sur le mouvement composant.",
    )
    reason = fields.Selection([
        ("missing", "Oubli / besoin complémentaire"),
        ("broken", "Casse"),
        ("replacement", "Remplacement"),
        ("supplier_error", "Erreur fournisseur"),
        ("other", "Autre"),
    ], string="Motif", default="missing", required=True)
    note = fields.Char(string="Commentaire")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        production = self.env["mrp.production"].browse(self.env.context.get("active_id"))
        if production:
            res["production_id"] = production.id
        return res

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for wizard in self:
            if wizard.product_id:
                wizard.product_uom_id = wizard.product_id.uom_id

    def action_add_need(self):
        self.ensure_one()
        production = self.production_id
        product = self.product_id

        if not production:
            raise UserError(_("Aucun ordre de fabrication sélectionné."))
        if production.state in ("done", "cancel"):
            raise UserError(_("Impossible d'ajouter un besoin sur un OF terminé ou annulé."))
        if not product:
            raise UserError(_("Veuillez sélectionner un article."))
        if self.product_qty <= 0:
            raise UserError(_("La quantité doit être supérieure à zéro."))
        if product.type not in ("product", "consu"):
            raise UserError(_("Seuls les articles stockables ou consommables peuvent être ajoutés comme besoin composant."))

        # On rattache le besoin au même groupe d'approvisionnement que l'OF/SO.
        # Si l'OF n'a pas encore de groupe, on en crée un afin de conserver le chaînage.
        group = production.procurement_group_id
        if not group:
            group = self.env["procurement.group"].create({
                "name": production.origin or production.name,
                "move_type": "direct",
                "company_id": production.company_id.id,
            })
            production.procurement_group_id = group.id

        # Emplacements : on reprend en priorité ceux des composants existants de l'OF.
        reference_raw_move = production.move_raw_ids[:1]
        location_src = production.location_src_id
        location_dest = reference_raw_move.location_dest_id if reference_raw_move else False
        if not location_dest:
            location_dest = production.picking_type_id.default_location_dest_id
        if not location_dest:
            location_dest = production.location_src_id

        route_ids = []
        if "route_ids" in product._fields:
            route_ids += product.route_ids.ids
        if product.categ_id and "total_route_ids" in product.categ_id._fields:
            route_ids += product.categ_id.total_route_ids.ids

        move_vals = {
            "name": "%s - %s" % (production.name, product.display_name),
            "product_id": product.id,
            "product_uom_qty": self.product_qty,
            "product_uom": self.product_uom_id.id,
            "raw_material_production_id": production.id,
            "group_id": group.id,
            "origin": production.origin or production.name,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": production.company_id.id,
            "date": self.date_planned or fields.Datetime.now(),
        }
        if route_ids and "route_ids" in self.env["stock.move"]._fields:
            move_vals["route_ids"] = [(6, 0, list(set(route_ids)))]
        if "warehouse_id" in self.env["stock.move"]._fields and production.picking_type_id.warehouse_id:
            move_vals["warehouse_id"] = production.picking_type_id.warehouse_id.id

        move = self.env["stock.move"].create(move_vals)

        # Sur un OF déjà confirmé, créer le composant ne relance pas toujours les approvisionnements.
        # On confirme le mouvement, puis on lance explicitement procurement.group.run() lorsque
        # le produit est MTO ou lorsqu'il manque du stock sur l'emplacement source et qu'une route
        # d'achat/fabrication existe. Le mouvement créé est passé en move_dest_ids afin que le RFQ/PO
        # généré reste chaîné à l'OF et au SO via le procurement group.
        try:
            move._action_confirm(merge=False)
        except TypeError:
            move._action_confirm()

        routes = self.env["stock.route"].browse(list(set(route_ids))) if route_ids else self.env["stock.route"]
        route_rules = routes.mapped("rule_ids")
        has_mto_route = any(rule.procure_method == "make_to_order" for rule in route_rules)
        has_supply_route = any(rule.action in ("buy", "manufacture") for rule in route_rules)

        available_qty = 0.0
        try:
            available_qty = self.env["stock.quant"]._get_available_quantity(product, location_src)
        except Exception:
            available_qty = 0.0

        should_run_procurement = has_mto_route or (has_supply_route and available_qty < self.product_qty)

        if should_run_procurement:
            warehouse = production.picking_type_id.warehouse_id
            procurement_values = {
                "company_id": production.company_id,
                "group_id": group,
                "warehouse_id": warehouse,
                "date_planned": self.date_planned or fields.Datetime.now(),
                "date_deadline": self.date_planned or fields.Datetime.now(),
                "move_dest_ids": move,
                "priority": getattr(production, "priority", "0") or "0",
            }
            if routes:
                procurement_values["route_ids"] = routes

            procurement = self.env["procurement.group"].Procurement(
                product,
                self.product_qty,
                self.product_uom_id,
                location_src,
                move.name,
                production.origin or production.name,
                production.company_id,
                procurement_values,
            )
            try:
                self.env["procurement.group"].run([procurement], raise_user_error=False)
            except TypeError:
                self.env["procurement.group"].run([procurement])

        # Réservation immédiate si du stock est disponible.
        try:
            move._action_assign()
        except Exception:
            # La réservation ne doit pas bloquer la création du besoin.
            pass

        # Trace métier dans le chatter de l'OF.
        reason_label = dict(self._fields["reason"].selection).get(self.reason, self.reason)
        message = _(
            "Besoin complémentaire ajouté : %(qty)s %(uom)s de %(product)s.<br/>Motif : %(reason)s%(note)s"
        ) % {
            "qty": self.product_qty,
            "uom": self.product_uom_id.display_name,
            "product": product.display_name,
            "reason": reason_label,
            "note": "<br/>Commentaire : %s" % self.note if self.note else "",
        }
        production.message_post(body=message)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Besoin ajouté"),
                "message": _("Le besoin a été ajouté à l'OF. Les règles Odoo géreront stock, achat ou fabrication selon la configuration de l'article."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
