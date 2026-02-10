# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    macro_planned_start = fields.Datetime(
        string="Date debut calculée",
        copy=False,
        help="Date deb calculée."
    )
    def write(self, values):
        # Eviter récursion quand on met à jour nous-mêmes les autres WO
        if self.env.context.get("skip_shift_chain"):
            return super().write(values)

        trigger = "date_start" in values  # ton champ de planning
        old_starts = {}
        old_ends = {}

        if trigger:
            for wo in self:
                old_starts[wo.id] = fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None
                old_ends[wo.id] = fields.Datetime.to_datetime(wo.date_finished) if wo.date_finished else None

            _logger.info(
                "GANTT MOVE (BEFORE super.write) | WO ids=%s | values=%s",
                self.ids, values
            )
            for wo in self:
                _logger.info(
                    "  BEFORE | WO %s(id=%s) | state=%s | op_seq=%s | wc=%s | start=%s | end=%s",
                    wo.name, wo.id, wo.state,
                    (wo.operation_id.sequence if wo.operation_id else None),
                    (wo.workcenter_id.display_name if wo.workcenter_id else None),
                    wo.date_start, wo.date_finished
                )

        res = super().write(values)

        if trigger:
            for wo in self:
                old_start = old_starts.get(wo.id)
                new_start = fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None
                if not old_start or not new_start:
                    _logger.warning(
                        "SKIP delta | WO %s(id=%s) | old_start=%s new_start=%s",
                        wo.name, wo.id, old_start, new_start
                    )
                    continue

                delta = new_start - old_start
                _logger.info(
                    "GANTT MOVE (AFTER super.write) | WO %s(id=%s) | old_start=%s -> new_start=%s | delta=%s",
                    wo.name, wo.id, old_start, new_start, delta
                )

                if not delta:
                    continue

                wo._shift_following_workorders(delta)

        return res

    def _shift_workorders_after(self, cutoff_start, delta):
        """Décale toutes les WO du même OF dont date_start >= cutoff_start (sauf la WO déplacée)."""
        self.ensure_one()
        mo = self.production_id
        if not mo:
            return
    
        cutoff_start = fields.Datetime.to_datetime(cutoff_start)
    
        # WO à décaler : toutes celles qui commencent après l'ancienne date
        targets = mo.workorder_ids.filtered(lambda w: (
            w.state not in ("done", "cancel")
            and w.id != self.id
            and w.date_start
            and fields.Datetime.to_datetime(w.date_start) >= cutoff_start
        ))
    
        # tri par date_start (logique "planning")
        targets = targets.sorted(lambda w: (fields.Datetime.to_datetime(w.date_start), w.id))
    
        _logger.info(
            "SHIFT AFTER | MO %s | moved=%s(%s) | cutoff=%s | delta=%s | targets=%s",
            mo.name, self.name, self.id, cutoff_start, delta, targets.ids
        )
    
        for wo in targets:
            old_start = fields.Datetime.to_datetime(wo.date_start)
            old_end = fields.Datetime.to_datetime(wo.date_finished) if wo.date_finished else None
    
            # conserver la durée actuelle pour éviter les changements de barre
            if old_end and old_end >= old_start:
                duration = old_end - old_start
            else:
                duration = timedelta(minutes=(wo.duration_expected or 0.0))
    
            new_start = old_start + delta
            new_end = new_start + duration
    
            wo.with_context(skip_shift_chain=True, mail_notrack=True).write({
                "date_start": new_start,
                "date_finished": new_end,
            })
    
            _logger.info(
                "  SHIFT OK | WO %s(%s) | %s -> %s",
                wo.name, wo.id, old_start, new_start
            )
