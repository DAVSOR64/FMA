# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Business rules migrated from Odoo Studio automations / server actions.

Origin (Studio, staging DB, audited 2026-07-02):
- base.automation "Bloquer la confirmation de devis si pas de CGV et RIB"
- base.automation "Client bloqué"
- base.automation "MAJ Champs Mtt A facturer"
- ir.actions.server "Recalculer 'Restant HT (pivot)'" (button)
- ir.actions.server "Calcul PRI" (button, id 1214) and its orphan batch
  variant (id 1215, never bound to a cron or a button) -> merged here into
  one engine with both a button and a cron entry point.
See STUDIO_AUDIT.md at the repo root for the full inventory.
"""
import datetime

from odoo import _, api, models
from odoo.exceptions import UserError

VITRAGE_CATEG_NAMES = ("all vitrage", "All / 02_REMPLISSAGE")

FIELD_ACHAT_MATIERE = "so_achat_matiere_reel"
FIELD_ACHAT_VITRAGE = "so_achat_vitrage_reel"
FIELD_COUT_APPRO_AFFAIRE = "x_studio_so_cout_appro_affaire"
FIELD_COUT_APPRO_STOCK = "x_studio_so_cout_appro_stock"
FIELD_APPRO_TOTAL = "x_studio_montant_total_appro"
FIELD_APPRO_NOT_DEL_NOT_INV = "x_studio_montant_non_livr_non_factur"
FIELD_APPRO_DEL_NOT_INV = "x_studio_montant_livr_non_factur"
FIELD_APPRO_DEL_INV = "x_studio_montant_livr_factur"

PRI_FIELDS = (
    FIELD_ACHAT_MATIERE,
    FIELD_ACHAT_VITRAGE,
    FIELD_COUT_APPRO_AFFAIRE,
    FIELD_COUT_APPRO_STOCK,
    FIELD_APPRO_TOTAL,
    FIELD_APPRO_NOT_DEL_NOT_INV,
    FIELD_APPRO_DEL_NOT_INV,
    FIELD_APPRO_DEL_INV,
)


def _categ_full_name(categ):
    return categ.complete_name or categ.name or ""


def _is_vitrage(product):
    categ = product.categ_id
    return _categ_full_name(categ) in VITRAGE_CATEG_NAMES or (categ.name or "") in VITRAGE_CATEG_NAMES


def _qty_move_consumed(move):
    return move.quantity or move.product_uom_qty or 0.0


def _has_bom(product, env):
    return bool(
        env["mrp.bom"].search(
            ["|", ("product_id", "=", product.id), ("product_tmpl_id", "=", product.product_tmpl_id.id)],
            limit=1,
        )
    )


def _po_unit_in_sale_currency_uom(pol, sale_currency, company, target_uom):
    unit = pol.price_unit
    if pol.currency_id != sale_currency:
        conv_date = pol.order_id.date_order or datetime.date.today()
        unit = pol.currency_id._convert(unit, sale_currency, company, conv_date)
    if pol.product_uom != target_uom:
        unit = pol.product_uom._compute_price(unit, target_uom)
    discount = pol.discount or 0.0
    if discount:
        unit = unit * (1.0 - discount / 100.0)
    return unit


def _pol_qty_received_or_ordered(pol):
    return pol.qty_received or pol.product_qty or 0.0


def _cost_from_pols(pols, sale_currency, company, target_uom, qty_of):
    if not pols:
        return 0.0
    if len(pols) == 1:
        unit = _po_unit_in_sale_currency_uom(pols[0], sale_currency, company, target_uom)
        return unit * qty_of
    total = 0.0
    for pol in pols:
        qty = _pol_qty_received_or_ordered(pol)
        if qty > 0:
            unit = _po_unit_in_sale_currency_uom(pol, sale_currency, company, target_uom)
            total += unit * qty
    return total


def _appro_breakdown(pols, sale_currency, company, target_uom):
    total = not_del_not_inv = del_not_inv = del_inv = 0.0
    for pol in pols:
        unit = _po_unit_in_sale_currency_uom(pol, sale_currency, company, target_uom)
        qty = _pol_qty_received_or_ordered(pol)
        amt = unit * qty
        qty_rec = pol.qty_received or 0.0
        qty_inv = pol.qty_invoiced or 0.0
        total += amt
        if qty_rec == 0 and qty_inv == 0:
            not_del_not_inv += amt
        elif qty_rec > 0 and qty_inv == 0:
            del_not_inv += amt
        elif qty_rec > 0 and qty_inv > 0:
            del_inv += amt
    return total, not_del_not_inv, del_not_inv, del_inv


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._check_studio_client_bloque()
        orders.with_context(skip_studio_sync=True)._sync_studio_montant_a_facturer()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state") == "draft":
            self._check_studio_client_bloque()
        if not self.env.context.get("skip_studio_sync"):
            self.with_context(skip_studio_sync=True)._sync_studio_montant_a_facturer()
        return res

    def action_confirm(self):
        for order in self:
            if not order.partner_id.x_studio_cgv_rib:
                raise UserError(
                    _("Impossible de confirmer le devis.\n\nLe client n'a pas validé les CGV + RIB.")
                )
        return super().action_confirm()

    def _check_studio_client_bloque(self):
        for order in self:
            if order.state == "draft" and order.partner_id.x_studio_client_bloque:
                raise UserError(_("Impossible de créer un devis.\n\nCe client est bloqué."))

    def _sync_studio_montant_a_facturer(self):
        for order in self:
            if order.so_mtt_facturer_reel != order.amount_untaxed:
                order.so_mtt_facturer_reel = order.amount_untaxed

    def action_recalculer_restant_ht(self):
        """Port of the "Recalculer 'Restant HT (pivot)'" Studio button."""
        orders = self or self.search([])
        for order in orders:
            try:
                val = float(order.x_studio_calcul_raf_ht or 0.0)
            except (TypeError, ValueError):
                val = 0.0
            order.x_studio_restant_a_facturer_ht_pivot = val

    def action_calcul_pri(self):
        """Port of the "Calcul PRI" Studio button (id 1214)."""
        self._compute_pri()

    @api.model
    def cron_calcul_pri_batch(self):
        """Port of the orphan batch variant of "Calcul PRI" (id 1215):
        recompute PRI for every confirmed/done sale order that has at least
        one non-cancelled manufacturing order referencing it.
        """
        mos = self.env["mrp.production"].search([("state", "!=", "cancel")])
        so_names_with_mo = {mo.origin.strip() for mo in mos if mo.origin}
        sales_to_process = self.search([("state", "in", ("sale", "done"))]).filtered(
            lambda s: s.name in so_names_with_mo
        )
        for order in sales_to_process:
            try:
                order._compute_pri()
                self.env.cr.commit()
            except Exception as e:
                self.env["ir.logging"].sudo().create(
                    {
                        "name": "fma_custom.sale_order",
                        "type": "server",
                        "level": "ERROR",
                        "message": "[Calcul PRI] Erreur sur %s : %s" % (order.name, e),
                        "path": "cron_calcul_pri_batch",
                        "func": "cron_calcul_pri_batch",
                        "line": "0",
                    }
                )
                self.env.cr.rollback()

    def _pols_for_pri(self):
        self.ensure_one()
        project = self.x_studio_projet
        if not project:
            return self.env["purchase.order.line"]
        return self.env["purchase.order.line"].search(
            [
                ("order_id.state", "in", ("purchase", "done")),
                ("order_id.x_studio_projet_du_so", "=", project.id),
            ]
        )

    def _compute_pri(self):
        for order in self:
            vals0 = {f: 0.0 for f in PRI_FIELDS if f in order._fields}
            if vals0:
                order.write(vals0)

            total_matiere = total_vitrage = total_affaire = total_stock = 0.0
            appro_total = appro_not_del_not_inv = appro_del_not_inv = appro_del_inv = 0.0

            all_pols = order._pols_for_pri()
            pols_by_product = {}
            for pol in all_pols:
                pols_by_product.setdefault(pol.product_id.id, []).append(pol)

            mos = self.env["mrp.production"].search(
                [("state", "!=", "cancel"), ("origin", "ilike", order.name)]
            )
            mos_by_finished = {}
            for mo in mos:
                if mo.product_id:
                    mos_by_finished.setdefault(mo.product_id.id, []).append(mo)

            lines = order.order_line.filtered(
                lambda l: l.product_id and not l.display_type and l.product_uom_qty > 0
            )

            for sol in lines:
                product = sol.product_id
                qty_sol = sol.product_uom_qty
                uom_sol = sol.product_uom

                if _has_bom(product, self.env):
                    mo_list = mos_by_finished.get(product.id) or mos
                    if not mo_list:
                        cost = product.standard_price * qty_sol
                        if _is_vitrage(product):
                            total_vitrage += cost
                        else:
                            total_matiere += cost
                        total_stock += cost
                        continue

                    for mo in mo_list:
                        moves = mo.move_raw_ids.filtered(lambda m: m.state != "cancel" and m.product_id)
                        qty_by_product_move = {}
                        uom_by_product_move = {}
                        for move in moves:
                            qty_comp = _qty_move_consumed(move)
                            if qty_comp <= 0:
                                continue
                            pid = move.product_id.id
                            qty_by_product_move[pid] = qty_by_product_move.get(pid, 0.0) + qty_comp
                            uom_by_product_move[pid] = move.product_uom

                        move_product_ids = set(qty_by_product_move.keys())

                        for pid, qty_total in qty_by_product_move.items():
                            comp = self.env["product.product"].browse(pid)
                            uom_comp = uom_by_product_move[pid]
                            candidates = pols_by_product.get(pid) or []

                            if not candidates:
                                cost = comp.standard_price * qty_total
                                if _is_vitrage(comp):
                                    total_vitrage += cost
                                else:
                                    total_matiere += cost
                                total_stock += cost
                            else:
                                cost = _cost_from_pols(
                                    candidates, order.currency_id, order.company_id, uom_comp, qty_total
                                )
                                if _is_vitrage(comp):
                                    total_vitrage += cost
                                else:
                                    total_matiere += cost
                                total_affaire += cost

                                t, ndni, dni, di = _appro_breakdown(
                                    candidates, order.currency_id, order.company_id, uom_comp
                                )
                                appro_total += t
                                appro_not_del_not_inv += ndni
                                appro_del_not_inv += dni
                                appro_del_inv += di

                        consu_already = set()
                        for pol in all_pols:
                            prod = pol.product_id
                            if not prod or prod.id in move_product_ids or prod.id in consu_already:
                                continue
                            if prod.type != "consu":
                                continue
                            consu_already.add(prod.id)
                            uom_pol = pol.product_uom
                            qty_pol = _pol_qty_received_or_ordered(pol)
                            cost = _cost_from_pols(
                                [pol], order.currency_id, order.company_id, uom_pol, qty_pol
                            )
                            total_matiere += cost
                            total_affaire += cost

                            t, ndni, dni, di = _appro_breakdown(
                                [pol], order.currency_id, order.company_id, uom_pol
                            )
                            appro_total += t
                            appro_not_del_not_inv += ndni
                            appro_del_not_inv += dni
                            appro_del_inv += di
                    continue

                candidates = pols_by_product.get(product.id) or []
                if not candidates:
                    cost = product.standard_price * qty_sol
                    if _is_vitrage(product):
                        total_vitrage += cost
                    else:
                        total_matiere += cost
                    total_stock += cost
                else:
                    cost = _cost_from_pols(candidates, order.currency_id, order.company_id, uom_sol, qty_sol)
                    if _is_vitrage(product):
                        total_vitrage += cost
                    else:
                        total_matiere += cost
                    total_affaire += cost

                    t, ndni, dni, di = _appro_breakdown(
                        candidates, order.currency_id, order.company_id, uom_sol
                    )
                    appro_total += t
                    appro_not_del_not_inv += ndni
                    appro_del_not_inv += dni
                    appro_del_inv += di

            vals = {}
            if FIELD_ACHAT_MATIERE in order._fields:
                vals[FIELD_ACHAT_MATIERE] = total_matiere
            if FIELD_ACHAT_VITRAGE in order._fields:
                vals[FIELD_ACHAT_VITRAGE] = total_vitrage
            if FIELD_COUT_APPRO_AFFAIRE in order._fields:
                vals[FIELD_COUT_APPRO_AFFAIRE] = total_affaire
            if FIELD_COUT_APPRO_STOCK in order._fields:
                vals[FIELD_COUT_APPRO_STOCK] = total_stock
            if FIELD_APPRO_TOTAL in order._fields:
                vals[FIELD_APPRO_TOTAL] = appro_total
            if FIELD_APPRO_NOT_DEL_NOT_INV in order._fields:
                vals[FIELD_APPRO_NOT_DEL_NOT_INV] = appro_not_del_not_inv
            if FIELD_APPRO_DEL_NOT_INV in order._fields:
                vals[FIELD_APPRO_DEL_NOT_INV] = appro_del_not_inv
            if FIELD_APPRO_DEL_INV in order._fields:
                vals[FIELD_APPRO_DEL_INV] = appro_del_inv
            if vals:
                order.write(vals)
