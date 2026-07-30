# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Business rules migrated from Odoo Studio automations.

Origin (Studio):
- base.automation "MTN : Propagation du compte analytique SO sur PO" and its
  exact duplicate "MTN : Propagation du compte analytique MO sur PO" (merged
  here into a single method).
- base.automation "DSA Reference compute PO" (also fixes a latent bug in the
  original code: it looped `for po in records` but read/wrote `record`
  instead of `po`, so it only behaved correctly for single-record triggers).
- base.automation "DSA : Mise à jour du responsable PO par le responsable
  PROJECT".
See STUDIO_AUDIT.md at the repo root for the full inventory.
"""
from odoo import models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def create(self, vals_list):
        orders = super().create(vals_list)
        orders.with_context(skip_studio_sync=True)._apply_studio_automations()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_studio_sync"):
            self.with_context(skip_studio_sync=True)._apply_studio_automations()
        return res

    def _apply_studio_automations(self):
        self._propagate_analytic_from_sale_order()
        self._compute_studio_reference()
        self._sync_responsible_from_project()

    def _propagate_analytic_from_sale_order(self):
        # Ne touche jamais une ligne qui a déjà une répartition analytique
        # (saisie manuelle ou propagation précédente) -- même règle que pour
        # "Projet du SO" (custom/models/purchase_order.py). Sans cette
        # garde, `write()` réappliquerait la répartition du devis à
        # *toutes* les lignes à chaque sauvegarde, effaçant silencieusement
        # toute correction manuelle.
        #
        # Cas particulier : une ligne ajoutée à la main sur une commande
        # déjà générée depuis la fabrication ne récupère rien de la source
        # ci-dessous seule. Cause : les lignes déjà présentes sur ce type de
        # commande héritent leur répartition analytique directement via la
        # chaîne d'approvisionnement standard (OF -> commande), sans qu'elle
        # soit jamais recopiée sur la ligne de devis -- la source lue
        # ci-dessous (`sale_order.order_line`) est donc vide, alors que la
        # commande elle-même a déjà la bonne valeur sur ses autres lignes.
        # On élargit donc la source de repli à ces lignes-sœurs déjà
        # renseignées sur la même commande.
        for po in self:
            analytic_dist = {}
            for line in po.order_line:
                if line.analytic_distribution:
                    analytic_dist = line.analytic_distribution
                    break
            if not analytic_dist and po.sale_order_count:
                sale_order = po._get_sale_orders()[:1]
                for sol in sale_order.order_line:
                    if sol.analytic_distribution:
                        analytic_dist = sol.analytic_distribution
                        break
            if not analytic_dist:
                continue
            lines_without_dist = po.order_line.filtered(lambda l: not l.analytic_distribution)
            if lines_without_dist:
                lines_without_dist.write({"analytic_distribution": analytic_dist})

    def _compute_studio_reference(self):
        for po in self:
            function = po.user_id.function or ""
            affaire = po.x_studio_many2one_field_LCOZX
            projet = po.x_studio_projet_du_so
            if projet:
                po.x_studio_rfrence = f"{function} - {projet.name} - {po.name}"
            elif affaire.x_name:
                po.x_studio_rfrence = f"{function} - {affaire.x_name} - {po.name}"
            else:
                po.x_studio_rfrence = f"{function} - {po.name}"

    def _sync_responsible_from_project(self):
        for po in self:
            projet = po.x_studio_projet_du_so
            po.user_id = projet.user_id if projet and projet.user_id else False
