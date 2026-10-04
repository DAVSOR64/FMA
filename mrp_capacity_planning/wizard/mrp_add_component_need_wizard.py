# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import Command, api, fields, models, _
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

        # Le besoin est ajouté EXACTEMENT comme une ligne saisie dans l'onglet
        # Composants : on écrit sur move_raw_ids, et c'est le standard qui
        # fait le reste (mrp.production.write -> _autoconfirm_production).
        #
        # L'ancienne version construisait le mouvement à la main et lançait
        # l'approvisionnement par procurement.group. Ce modèle N'EXISTE PLUS
        # en v19, pas plus que stock.move.group_id : le bouton plantait dès la
        # première ligne. Les références d'approvisionnement sont désormais
        # des stock.reference, posées sur le mouvement par l'OF lui-même, et
        # les règles se lancent par stock.rule — ce que fait la confirmation
        # du mouvement, sans qu'on ait à le refaire ici.
        #
        # Sur un OF confirmé, le standard :
        #   - arrête la méthode d'appro du composant (_adjust_procure_method) ;
        #   - le confirme, ce qui crée le prélèvement Stock -> Pré-Fab en
        #     fabrication à deux étapes, rattaché au bon de l'OF s'il est
        #     encore ouvert ;
        #   - déclenche l'achat ou la fabrication si les routes de l'article
        #     le demandent (à la commande + acheter).
        # Sur un OF en brouillon, le composant attend la confirmation de l'OF.
        move_vals = production._get_move_raw_values(
            product, self.product_qty, self.product_uom_id)
        if self.date_planned:
            move_vals["date"] = self.date_planned
            move_vals["date_deadline"] = self.date_planned

        avant = production.move_raw_ids
        production.write({"move_raw_ids": [Command.create(move_vals)]})
        # Le mouvement peut avoir été fondu dans un composant identique à la
        # confirmation : on ne garde que ce qui existe encore.
        move = (production.move_raw_ids - avant).exists()

        # Réservation immédiate si du stock est disponible.
        if move and production.state != "draft":
            try:
                with self.env.cr.savepoint():
                    move._action_assign()
            except Exception:
                # La réservation ne doit pas bloquer la création du besoin.
                pass

        # Trace métier dans le chatter de l'OF.
        reason_label = dict(self._fields["reason"].selection).get(self.reason, self.reason)
        # Markup : en v19 un corps de message en texte simple est échappé, et
        # le saut de ligne s'affichait tel quel, « <br/> » compris. Les
        # valeurs saisies, elles, restent échappées.
        message = Markup(_(
            "Besoin complémentaire ajouté : %(qty)s %(uom)s de %(product)s.<br/>Motif : %(reason)s%(note)s"
        )) % {
            "qty": self.product_qty,
            "uom": self.product_uom_id.display_name,
            "product": product.display_name,
            "reason": reason_label,
            "note": Markup("<br/>Commentaire : %s") % self.note if self.note else "",
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
