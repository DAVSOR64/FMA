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

        # Destinataires dynamiques :
        # - client/contact principal : sale.order.main_contact_id
        # - bureau d'étude : sale.order.x_studio_bureau_dtude (res.users)
        # - commercial : sale.order.x_studio_commercial_1 (nom dans un champ Char)
        partner_ids = [contact.id]

        # Bureau d'étude : many2one vers res.users.
        be_user = getattr(sale_order, "x_studio_bureau_dtude", False)
        if be_user and be_user.partner_id and be_user.partner_id.email:
            partner_ids.append(be_user.partner_id.id)

        # Commercial : champ Char contenant le nom du commercial.
        commercial_name = getattr(sale_order, "x_studio_commercial_1", False)
        if commercial_name:
            employee = self.env["hr.employee"].search(
                [("name", "=", commercial_name)],
                limit=1,
            )
            if not employee:
                employee = self.env["hr.employee"].search(
                    [("name", "ilike", commercial_name)],
                    limit=1,
                )

            if employee:
                # Selon les versions Odoo / configuration RH, le partenaire peut être porté par :
                # - work_contact_id : contact professionnel de l'employé,
                # - user_id.partner_id : utilisateur lié,
                # - address_home_id : contact privé, en dernier recours uniquement.
                commercial_partner = False

                if hasattr(employee, "work_contact_id") and employee.work_contact_id:
                    commercial_partner = employee.work_contact_id
                elif employee.user_id and employee.user_id.partner_id:
                    commercial_partner = employee.user_id.partner_id
                elif employee.address_home_id:
                    commercial_partner = employee.address_home_id

                # Si aucun partenaire n'est trouvé mais qu'un email existe sur l'employé,
                # on recherche un res.partner correspondant afin de pouvoir l'ajouter
                # dans le même champ destinataire que le client.
                commercial_email = (
                    employee.work_email
                    or employee.user_id.email
                    or (commercial_partner.email if commercial_partner else False)
                )

                if not commercial_partner and commercial_email:
                    commercial_partner = self.env["res.partner"].search(
                        [("email", "=", commercial_email)],
                        limit=1,
                    )

                if commercial_partner and commercial_partner.email:
                    partner_ids.append(commercial_partner.id)

        # Déduplication en conservant l'ordre.
        partner_ids = list(dict.fromkeys(partner_ids))

        ctx = {
            "default_model": "stock.picking",
            "default_res_ids": [self.id],
            "default_composition_mode": "comment",
            "force_email": True,
            "default_partner_ids": [(6, 0, partner_ids)],
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
