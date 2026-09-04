# -*- coding: utf-8 -*-
"""Wizard de depot du fichier de chiffrage, lance depuis le devis.

Le wizard ne reimplemente pas la lecture du fichier : il cree un
enregistrement ``sqlite.connector`` — qui reste le moteur d'import et le
journal consultable — en lui passant le devis cible, puis declenche
l'import.
"""
import base64
import logging
import os
import tempfile

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FmaPricerImportWizard(models.TransientModel):
    _name = "fma.pricer.import.wizard"
    _description = "Import Pricer dans un devis"

    order_id = fields.Many2one(
        "sale.order",
        string="Devis",
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related="order_id.partner_id",
        string="Client",
    )
    file = fields.Binary(
        string="Fichier de chiffrage",
        required=True,
        help="Export LOGIKAL (base SQLite) ou TechDesign (XML de chiffrage "
             "ou de commande fournisseur). Le format est reconnu au contenu "
             "du fichier, pas a son extension.",
    )
    filename = fields.Char(string="Nom du fichier")
    description = fields.Char(
        string="Description",
        help="Libelle de l'import dans le journal SQLite Connector.",
    )
    replace_lines = fields.Boolean(
        string="Remplacer les lignes existantes",
        help="Supprime les lignes actuelles du devis avant l'import. "
        "A utiliser pour reimporter un chiffrage corrige.",
    )
    create_lots = fields.Boolean(
        string="Creer les lots de fabrication",
        default=True,
        help="Cree le lot decrit par le fichier, repartit les quantites du "
        "devis sur ce lot et enregistre les barres optimisees comme besoin "
        "matiere. A decocher pour un chiffrage sans mise en lot.",
    )
    existing_line_count = fields.Integer(
        string="Lignes actuelles",
        compute="_compute_existing_line_count",
    )

    def _compute_existing_line_count(self):
        for wizard in self:
            wizard.existing_line_count = len(
                wizard.order_id.order_line.filtered(lambda l: not l.display_type)
            )

    def action_import(self):
        self.ensure_one()
        order = self.order_id

        if order.state not in ("draft", "sent"):
            raise UserError(
                _(
                    "Le devis %(name)s est a l'etat %(state)s : l'import "
                    "Pricer n'est possible que sur un devis non confirme.",
                    name=order.display_name,
                    state=order.state,
                )
            )
        if not order.partner_id:
            raise UserError(
                _(
                    "Renseignez le client sur le devis %s avant d'importer "
                    "le chiffrage.",
                    order.display_name,
                )
            )

        if self.replace_lines and order.order_line:
            order.order_line.unlink()

        # Le connecteur SQLite est l'import historique : il ouvre le fichier
        # comme une base et en tire articles, nomenclature de projet et lignes
        # de devis. Il ne concerne que LOGIKAL — lui donner un XML le faisait
        # echouer sur « file is not a database ».
        connector = False
        if self._fichier_sqlite():
            connector = self.env["sqlite.connector"].create(
                {
                    "description": self.description
                    or _("Import Pricer %s", order.name),
                    "file": self.file,
                    "filename": self.filename,
                    "target_sale_order_id": order.id,
                }
            )

        order.message_post(
            body=_(
                "Import Pricer lance depuis le fichier %s.",
                self.filename or _("(sans nom)"),
            )
        )

        if connector:
            connector.export_data_from_db()
            if self.create_lots:
                self._import_lots(order)
        else:
            # Sur un export TechDesign, le pivot EST l'import : aucun
            # connecteur n'a pose les lignes en amont, et la case « creer les
            # lots » n'a donc pas a pouvoir le desactiver.
            self._import_lots(order)

        if connector:
            return {
                "type": "ir.actions.act_window",
                "name": _("Import Pricer"),
                "res_model": "sqlite.connector",
                "res_id": connector.id,
                "view_mode": "form",
                "target": "current",
            }
        # Pas de journal de connecteur a montrer : on rend la main sur le
        # devis, ou les lignes, les lots et les avertissements sont visibles.
        return {
            "type": "ir.actions.act_window",
            "name": _("Devis"),
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def _fichier_sqlite(self):
        """Vrai si le fichier depose est une base SQLite, donc un export LOGIKAL.

        Reconnu aux premiers octets et non a l'extension : un televersement ne
        garantit rien de son nom. Meme regle que l'aiguillage du moteur, pour
        que les deux ne puissent pas diverger.
        """
        self.ensure_one()
        contenu = base64.b64decode(self.file or b"")
        return contenu.startswith(b"SQLite format 3")

    def _import_lots(self, order):
        """Applique la mise en lot du fichier au devis.

        Les adaptateurs lisent un chemin : on materialise donc le binaire du
        wizard dans un fichier temporaire, supprime aussitot apres.
        """
        self.ensure_one()
        content = base64.b64decode(self.file or b"")
        if not content:
            return

        # Suffixe neutre : le fichier peut etre une base SQLite (LOGIKAL) ou
        # un XML (TechDesign). Le moteur reconnait le format a son contenu.
        handle, path = tempfile.mkstemp(suffix=".pricer", prefix="fma_pricer_")
        try:
            with os.fdopen(handle, "wb") as tmp:
                tmp.write(content)
            lots = self.env["fma.pricer.engine"].import_file(
                order, path, source=self.filename
            )
        finally:
            try:
                os.unlink(path)
            except OSError:  # pragma: no cover - nettoyage best effort
                _logger.warning("Fichier temporaire non supprime : %s", path)

        if lots:
            order.message_post(
                body=_(
                    "Mise en lot : %(names)s",
                    names=", ".join(lots.mapped("display_name")),
                )
            )
