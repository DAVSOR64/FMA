from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    delay_sale_order_id = fields.Many2one(
        "sale.order",
        string="Commande liée au retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )
    delay_arc = fields.Char(
        string="ARC retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )
    delay_ref_client = fields.Char(
        string="Référence client retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )
    delay_initial_date = fields.Date(
        string="Date initiale retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )
    delay_initial_week = fields.Char(
        string="Semaine initiale retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )
    delay_new_date = fields.Date(
        string="Nouvelle date retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )
    delay_new_week = fields.Char(
        string="Nouvelle semaine retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )
    delay_motif = fields.Char(
        string="Motif retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )
    delay_designation = fields.Char(
        string="Désignation retard",
        compute="_compute_delay_mail_values",
        store=True,
        readonly=True,
    )

    def _get_related_sale_order(self):
        self.ensure_one()

        if hasattr(self, "sale_id") and self.sale_id:
            return self.sale_id

        sale_orders = self.move_ids.sale_line_id.order_id
        sale_orders = sale_orders.filtered(lambda so: so)

        if len(sale_orders) == 1:
            return sale_orders

        if len(sale_orders) > 1:
            raise UserError("Plusieurs commandes clients liées à ce BL.")

        return False

    @api.depends(
        "sale_id",
        "date_deadline",
        "scheduled_date",
        "move_ids.sale_line_id.order_id",
        "move_ids.sale_line_id.order_id.so_retard_nouvelle_date",
        "move_ids.sale_line_id.order_id.so_date_de_livraison",
    )
    def _compute_delay_mail_values(self):
        for picking in self:
            try:
                sale_order = picking._get_related_sale_order()
            except UserError:
                sale_order = False

            values = {}
            if sale_order and hasattr(sale_order, "_get_retard_livraison_values"):
                values = sale_order._get_retard_livraison_values(picking=picking)
            elif sale_order:
                old_date = picking.date_deadline.date() if picking.date_deadline else False
                new_date = picking.scheduled_date.date() if picking.scheduled_date else False
                if not new_date:
                    new_date = getattr(sale_order, "so_retard_nouvelle_date", False) or False
                values = {
                    "arc": sale_order.name,
                    "ref_client": sale_order.client_order_ref or sale_order.name,
                    "old_date": old_date,
                    "old_week": old_date and str(old_date.isocalendar()[1]) or "",
                    "new_date": new_date,
                    "new_week": new_date and str(new_date.isocalendar()[1]) or "",
                    "motif": "",
                }

            motif = ""
            designation = ""
            if hasattr(picking, "so_retard_motif_level1_id") and picking.so_retard_motif_level1_id:
                motif = picking.so_retard_motif_level1_id.name
            elif values.get("motif"):
                motif = values.get("motif")

            if hasattr(picking, "so_retard_motif_level2_id") and picking.so_retard_motif_level2_id:
                designation = picking.so_retard_motif_level2_id.name

            picking.delay_sale_order_id = sale_order
            picking.delay_arc = values.get("arc") or ""
            picking.delay_ref_client = values.get("ref_client") or ""
            picking.delay_initial_date = values.get("old_date") or False
            picking.delay_initial_week = values.get("old_week") or ""
            picking.delay_new_date = values.get("new_date") or False
            picking.delay_new_week = values.get("new_week") or ""
            picking.delay_motif = motif
            picking.delay_designation = designation

    def action_open_delay_email(self):
        self.ensure_one()

        # Recalcule explicitement les semaines juste avant l'ouverture
        # de l'assistant mail, afin que le template standard Odoo récupère
        # toujours les dates à jour.
        self._compute_delay_mail_values()

        sale_order = self._get_related_sale_order()
        if not sale_order:
            raise UserError("Aucun SO lié.")

        contact = getattr(sale_order, "main_contact_id", False) or sale_order.partner_id
        if not contact:
            raise UserError("Pas de contact principal ou de client lié.")

        if not contact.email:
            raise UserError("Contact sans email.")

        # Template standard Odoo créé manuellement.
        # On le recherche par modèle + nom afin d'éviter de dépendre d'un XML ID.
        template = self.env["mail.template"].search(
            [
                ("model", "=", "stock.picking"),
                ("name", "ilike", "info retard"),
            ],
            limit=1,
        )

        ctx = {
            "default_model": "stock.picking",
            "default_res_ids": [self.id],
            "default_composition_mode": "comment",
            "force_email": True,
            "default_partner_ids": [(6, 0, [contact.id])],
        }

        if template:
            ctx.update(
                {
                    "default_use_template": True,
                    "default_template_id": template.id,
                }
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Information retard",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }
