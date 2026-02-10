# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields

_logger = logging.getLogger(__name__)

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def write(self, values):
        # éviter récursion quand on décale nous-mêmes
        if self.env.context.get("skip_shift_chain"):
            return super().write(values)

        # Déclencheur principal = déplacement dans le Gantt
        trigger = "date_planned_start" in values

        old_starts = {}
        if trigger:
            for wo in self:
                old_starts[wo.id] = fields.Datetime.to_datetime(wo.date_planned_start) if wo.date_planned_start else None

        res = super().write(values)

        if trigger:
            for wo in self:
                old_start = old_starts.get(wo.id)
                new_start = fields.Datetime.to_datetime(wo.date_planned_start) if wo.date_planned_start else None
                if not old_start or not new_start:
                    continue

                delta = new_start - old_start
                if not delta:
                    continue

                wo._shift_following_workorders_planned(delta)

        return res

    def _shift_following_workorders_planned(self, delta):
        """Décale toutes les WO suivantes du même delta sur les champs planifiés."""
        self.ensure_one()
        mo = self.production_id
        if not mo:
            return

        # WO actives
        wos = mo.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))

        # Tri : opération.sequence puis id (comme ton macro)
        wos = sorted(wos, key=lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        # index de la WO déplacée
        try:
            idx = next(i for i, w in enumerate(wos) if w.id == self.id)
        except StopIteration:
            return

        following = wos[idx + 1:]

        # ✅ on garde macro aligné avec le planning déplacé
        if "macro_planned_start" in self._fields:
            self.with_context(skip_shift_chain=True, mail_notrack=True).write({
                "macro_planned_start": self.date_planned_start,
            })

        for wo in following:
            if not wo.date_planned_start:
                # si une WO n'était pas planifiée, tu peux choisir:
                # - soit continuer (ne pas la toucher)
                # - soit la chaîner (je te propose la version "continue" pour rester proche de ton avant)
                continue

            start_dt = fields.Datetime.to_datetime(wo.date_planned_start) + delta
            duration_min = wo.duration_expected or 0.0
            end_dt = start_dt + timedelta(minutes=duration_min)

            vals = {
                "date_planned_start": start_dt,
                "date_planned_finished": end_dt,
            }
            if "macro_planned_start" in wo._fields:
                vals["macro_planned_start"] = start_dt

            wo.with_context(skip_shift_chain=True, mail_notrack=True).write(vals)

        # (optionnel) si tu as une méthode qui recale l'OF
        if hasattr(mo, "_update_mo_dates_from_workorders_dates_only"):
            mo.with_context(skip_shift_chain=True, mail_notrack=True)._update_mo_dates_from_workorders_dates_only()
