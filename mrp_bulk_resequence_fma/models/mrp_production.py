# -*- coding: utf-8 -*-
import logging
import unicodedata

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    @api.model
    def _fma_operation_order_map(self):
        return {
            "debit fma": 10,
            "cu (banc) fma": 20,
            "usinage fma": 30,
            "montage fma": 40,
            "vitrage fma": 50,
            "emballage fma": 60,
        }

    @api.model
    def _normalize_fma_label(self, value):
        value = value or ""
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        return " ".join(value.lower().strip().split())

    def _get_fma_rank_for_workorder(self, wo):
        order_map = self._fma_operation_order_map()
        candidates = [
            wo.workcenter_id.display_name,
            wo.workcenter_id.name,
            wo.operation_id.name if wo.operation_id else False,
            wo.name,
        ]
        for candidate in candidates:
            key = self._normalize_fma_label(candidate)
            if key in order_map:
                return order_map[key]
        return 999

    def _is_not_started_for_bulk_resequence(self):
        self.ensure_one()
        if self.state in ("progress", "to_close", "done", "cancel"):
            return False
        started_wos = self.workorder_ids.filtered(lambda w: w.state in ("progress", "done"))
        return not started_wos

    def action_open_bulk_resequence_wizard(self):
        productions = self
        if not productions:
            raise UserError(_("Sélectionnez au moins un OF."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Réordonner opérations FMA"),
            "res_model": "mrp.bulk.resequence.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_production_ids": [(6, 0, productions.ids)],
            },
        }

    def action_bulk_resequence_fma(self):
        updated = 0
        skipped = []
        details = []

        for mo in self:
            if not mo._is_not_started_for_bulk_resequence():
                skipped.append(mo.name)
                continue

            workorders = mo.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
            if not workorders:
                skipped.append(mo.name)
                continue

            ranked_wos = workorders.sorted(lambda w: (mo._get_fma_rank_for_workorder(w), w.id))
            seq = 10
            for wo in ranked_wos:
                vals = {}
                if "sequence" in wo._fields:
                    vals["sequence"] = seq
                if wo.operation_id:
                    try:
                        wo.operation_id.with_context(mail_notrack=True).write({"sequence": seq})
                    except Exception:
                        _logger.exception("Impossible de mettre à jour la séquence opération pour %s", wo.display_name)
                if vals:
                    wo.with_context(skip_shift_chain=True, skip_macro_recalc=True, mail_notrack=True).write(vals)
                details.append("%s -> %s" % (wo.display_name, seq))
                seq += 10

            # Replanification locale uniquement pour cet OF
            fixed_end_dt = (
                getattr(mo, 'macro_forced_end', False)
                or mo.date_deadline
                or getattr(mo, 'date_finished', False)
            )
            if fixed_end_dt:
                ctx = mo.with_context(skip_macro_recalc=True, mail_notrack=True)
                try:
                    ctx._recalculate_macro_backward(ranked_wos, end_dt=fixed_end_dt)
                    ctx.apply_macro_to_workorders_dates()
                    ctx._update_mo_dates_from_macro(forced_end_dt=fixed_end_dt)
                    ctx._update_components_picking_dates()
                except Exception:
                    _logger.exception("Erreur de replanification locale sur %s", mo.name)
            updated += 1

        message = _("OF mis à jour : %s") % updated
        if skipped:
            message += "\n" + _("OF ignorés (déjà lancés / terminés) : %s") % ", ".join(skipped)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Réordonnancement FMA"),
                "message": message,
                "type": "success" if updated else "warning",
                "sticky": True,
            }
        }
