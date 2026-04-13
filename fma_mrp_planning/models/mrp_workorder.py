# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

ORDER_FMA = [
    "Débit FMA",
    "CU (banc) FMA",
    "Usinage FMA",
    "Montage FMA",
    "Vitrage FMA",
    "Emballage FMA",
]


def _norm(value):
    return (value or "").strip().lower()


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    # ── Champs macro planning ──────────────────────────────────────────────────
    macro_planned_start = fields.Datetime(
        string="Date début calculée",
        copy=False,
        help="Date de début calculée par le macro planning (rétroplanning).",
    )
    x_nb_resources = fields.Integer(
        string="Nb ressources",
        default=1,
        copy=False,
        help="Nombre de ressources appliquées sur cette opération.",
    )

    # ── Champ séquence opération (bulk resequence) ─────────────────────────────
    op_sequence = fields.Integer(
        string="Séquence opération",
        related="operation_id.sequence",
        store=True,
        readonly=True,
    )

    # ── Write : blocage des remises à False + décalage en chaîne ──────────────
    def write(self, values):
        if self.env.context.get("skip_shift_chain"):
            return super().write(values)

        # Bloquer les writes date_start/date_finished=False hors déprogrammation explicite
        if (
            values.get("date_start") is False or values.get("date_finished") is False
        ) and not self.env.context.get("allow_wo_clear"):
            _logger.info(
                "BLOCAGE write date_start/date_finished=False sur WO %s", self.ids
            )
            filtered = {
                k: v
                for k, v in values.items()
                if k not in ("date_start", "date_finished")
            }
            if filtered:
                return super().write(filtered)
            return True

        trigger = "date_start" in values
        old_starts = {}

        if trigger:
            for wo in self:
                old_starts[wo.id] = (
                    fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None
                )

        res = super().write(values)

        if trigger and not self.env.context.get('skip_macro_recalc'):
            for wo in self:
                old_start = old_starts.get(wo.id)
                new_start = (
                    fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None
                )
                if not old_start or not new_start:
                    continue
                delta = new_start - old_start
                if delta:
                    wo._shift_workorders_after(old_start, delta)

        return res

    def _shift_workorders_after(self, cutoff_start, delta):
        """Décale tous les WOs du même OF dont date_start >= cutoff_start."""
        self.ensure_one()
        mo = self.production_id
        if not mo:
            return

        cutoff_start = fields.Datetime.to_datetime(cutoff_start)
        targets = mo.workorder_ids.filtered(
            lambda w: (
                w.state not in ("done", "cancel")
                and w.id != self.id
                and w.date_start
                and fields.Datetime.to_datetime(w.date_start) >= cutoff_start
            )
        ).sorted(lambda w: (fields.Datetime.to_datetime(w.date_start), w.id))

        for wo in targets:
            old_start = fields.Datetime.to_datetime(wo.date_start)
            old_end = (
                fields.Datetime.to_datetime(wo.date_finished) if wo.date_finished else None
            )
            duration = (
                old_end - old_start
                if old_end and old_end >= old_start
                else timedelta(minutes=(wo.duration_expected or 0.0))
            )
            new_start = old_start + delta
            wo.with_context(skip_shift_chain=True, mail_notrack=True).write(
                {"date_start": new_start, "date_finished": new_start + duration}
            )

    # ── Réordonnancement FMA ───────────────────────────────────────────────────
    def _fma_rank(self):
        """Retourne le rang FMA de ce WO selon l'ordre des postes."""
        values = [
            _norm(self.name),
            _norm(self.workcenter_id.name),
            _norm(self.operation_id.name if self.operation_id else ""),
        ]
        for idx, label in enumerate(ORDER_FMA, start=1):
            if any(_norm(label) in val for val in values):
                return idx
        return 999
