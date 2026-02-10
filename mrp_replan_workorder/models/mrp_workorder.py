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

    def _shift_following_workorders(self, delta):
        """Décale toutes les WO suivantes du même delta sur date_start (et recale la fin en conservant la durée actuelle)."""
        self.ensure_one()
        mo = self.production_id
        if not mo:
            _logger.warning("SHIFT: no production_id on WO %s(id=%s)", self.name, self.id)
            return

        # WO actives
        all_wos = mo.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))

        # Tri : opération.sequence puis id (comme tes scripts macro)
        all_wos = sorted(all_wos, key=lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        _logger.info("SHIFT START | MO %s | moved WO %s(id=%s) | delta=%s | WO count=%s",
                     mo.name, self.name, self.id, delta, len(all_wos))

        for w in all_wos:
            _logger.info(
                "  CHAIN | WO %s(id=%s) | state=%s | op_seq=%s | start=%s | end=%s",
                w.name, w.id, w.state,
                (w.operation_id.sequence if w.operation_id else None),
                w.date_start, w.date_finished
            )

        # position WO déplacée
        try:
            idx = next(i for i, w in enumerate(all_wos) if w.id == self.id)
        except StopIteration:
            _logger.warning("SHIFT: moved WO %s(id=%s) not found in MO.workorder_ids", self.name, self.id)
            return

        following = all_wos[idx + 1:]
        _logger.info("SHIFT: following count=%s | ids=%s", len(following), [w.id for w in following])

        shifted = 0
        skipped_no_start = 0

        for wo in following:
            if not wo.date_start:
                skipped_no_start += 1
                _logger.warning(
                    "SHIFT SKIP (no date_start) | WO %s(id=%s) | op_seq=%s",
                    wo.name, wo.id, (wo.operation_id.sequence if wo.operation_id else None)
                )
                continue

            old_start = fields.Datetime.to_datetime(wo.date_start)
            old_end = fields.Datetime.to_datetime(wo.date_finished) if wo.date_finished else None

            # ✅ préserver la durée "réelle" affichée dans le planning
            if old_end and old_end >= old_start:
                duration = old_end - old_start
            else:
                # fallback si end vide/incohérent
                duration = timedelta(minutes=(wo.duration_expected or 0.0))

            new_start = old_start + delta
            new_end = new_start + duration

            wo.with_context(skip_shift_chain=True, mail_notrack=True).write({
                "date_start": new_start,
                "date_finished": new_end,
            })
            shifted += 1

            _logger.info(
                "SHIFT OK | WO %s(id=%s) | %s -> %s | duration_kept=%s | new_end=%s",
                wo.name, wo.id, old_start, new_start, duration, new_end
            )

        _logger.info(
            "SHIFT END | MO %s | moved WO %s(id=%s) | shifted=%s | skipped_no_start=%s",
            mo.name, self.name, self.id, shifted, skipped_no_start
        )
