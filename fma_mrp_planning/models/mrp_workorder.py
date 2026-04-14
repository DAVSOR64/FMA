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

# Palette Odoo approchée pour le gantt.
# L'index exact dépend du thème, mais cette table donne un rendu stable et lisible.
COLOR_BY_RANK = {
    1: 1,   # Débit   -> rouge
    2: 5,   # CU      -> bleu foncé
    3: 4,   # Usinage -> bleu clair
    4: 10,  # Montage -> vert
    5: 11,  # Vitrage -> violet
    6: 3,   # Emballage -> jaune
}


def _norm(value):
    return (value or "").strip().lower()


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    macro_planned_start = fields.Datetime(
        string="Date début calculée",
        copy=False,
        help="Date de début calculée par le macro planning (rétroplanning).",
    )
    macro_planned_finished = fields.Datetime(
        string="Date fin calculée",
        copy=False,
        help="Date de fin calculée par le macro planning (rétroplanning).",
    )
    x_nb_resources = fields.Integer(
        string="Nb ressources",
        default=1,
        copy=False,
        help="Nombre de ressources appliquées sur cette opération.",
    )
    op_sequence = fields.Integer(
        string="Séquence opération",
        related="operation_id.sequence",
        store=True,
        readonly=True,
    )

    project_display = fields.Char(string='Projet', compute='_compute_planning_labels', store=True)
    mtn_display = fields.Char(string='N° MTN', compute='_compute_planning_labels', store=True)
    color_index = fields.Integer(string='Couleur planning', compute='_compute_color_index', store=True)
    gantt_label = fields.Char(string='Label GANTT', compute='_compute_gantt_label', store=True)
    gantt_date_start = fields.Datetime(
        string='Début GANTT',
        compute='_compute_gantt_dates',
        store=True,
        help='Date de début pour le GANTT macro : macro_planned_start en priorité, sinon date_start',
    )
    gantt_date_stop = fields.Datetime(
        string='Fin GANTT',
        compute='_compute_gantt_dates',
        store=True,
        help='Date de fin pour le GANTT macro : date_finished ou calculée depuis durée',
    )

    def write(self, values):
        if self.env.context.get("skip_shift_chain"):
            return super().write(values)

        if (
            values.get("date_start") is False or values.get("date_finished") is False
        ) and not self.env.context.get("allow_wo_clear"):
            _logger.info("BLOCAGE write date_start/date_finished=False sur WO %s", self.ids)
            filtered = {k: v for k, v in values.items() if k not in ("date_start", "date_finished")}
            if filtered:
                return super().write(filtered)
            return True

        trigger = "date_start" in values
        old_starts = {}
        if trigger:
            for wo in self:
                old_starts[wo.id] = fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None

        res = super().write(values)

        if trigger and not self.env.context.get('skip_macro_recalc'):
            for wo in self:
                old_start = old_starts.get(wo.id)
                new_start = fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None
                if not old_start or not new_start:
                    continue
                delta = new_start - old_start
                if delta:
                    wo._shift_workorders_after(old_start, delta)

        return res

    def _shift_workorders_after(self, cutoff_start, delta):
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
            old_end = fields.Datetime.to_datetime(wo.date_finished) if wo.date_finished else None
            duration = old_end - old_start if old_end and old_end >= old_start else timedelta(minutes=(wo.duration_expected or 0.0))
            new_start = old_start + delta
            wo.with_context(skip_shift_chain=True, mail_notrack=True).write(
                {"date_start": new_start, "date_finished": new_start + duration}
            )

    def _fma_rank(self):
        values = [
            _norm(self.name),
            _norm(self.workcenter_id.name),
            _norm(self.operation_id.name if self.operation_id else ""),
        ]
        for idx, label in enumerate(ORDER_FMA, start=1):
            if any(_norm(label) in val for val in values):
                return idx
        return 999

    @api.depends('production_id', 'project_display')
    def _compute_gantt_label(self):
        for wo in self:
            mo_name = wo.production_id.name or ''
            projet = wo.project_display or ''
            wo.gantt_label = f"{mo_name} | {projet}" if projet and projet != 'Sans projet' else mo_name

    def name_get(self):
        result = []
        for wo in self:
            mo_name = wo.production_id.name or ''
            projet = wo.project_display or ''
            label = f"{mo_name} | {projet}" if projet and projet != 'Sans projet' else (mo_name or wo.name)
            result.append((wo.id, label))
        return result

    def _compute_display_name(self):
        for wo in self:
            mo_name = wo.production_id.name or ''
            projet = wo.project_display or ''
            wo.display_name = f"{mo_name} | {projet}" if projet and projet != 'Sans projet' else (mo_name or wo.name)

    @api.depends('macro_planned_start', 'macro_planned_finished', 'date_start', 'date_finished', 'duration_expected')
    def _compute_gantt_dates(self):
        for wo in self:
            start = getattr(wo, 'macro_planned_start', False) or wo.date_start
            wo.gantt_date_start = start
            stop = getattr(wo, 'macro_planned_finished', False) or wo.date_finished
            if not stop and start and wo.duration_expected:
                stop = start + timedelta(minutes=wo.duration_expected)
            wo.gantt_date_stop = stop

    @api.depends('production_id', 'production_id.name', 'production_id.origin', 'production_id.procurement_group_id')
    def _compute_planning_labels(self):
        SaleOrder = self.env['sale.order']
        for wo in self:
            mo = wo.production_id
            sale = False
            if mo:
                sale = getattr(getattr(mo, 'procurement_group_id', False), 'sale_id', False)
                if not sale and getattr(mo, 'origin', False):
                    sale = SaleOrder.search([('name', '=', mo.origin)], limit=1)

            project = False
            for candidate in (
                getattr(mo, 'x_studio_projet', False) if mo else False,
                getattr(sale, 'x_studio_projet', False) if sale else False,
                getattr(sale, 'project_id', False).display_name if sale and getattr(sale, 'project_id', False) else False,
                getattr(sale, 'analytic_account_id', False).display_name if sale and getattr(sale, 'analytic_account_id', False) else False,
                getattr(sale, 'name', False) if sale else False,
                getattr(mo, 'origin', False) if mo else False,
                getattr(mo, 'name', False) if mo else False,
            ):
                if candidate:
                    project = candidate.display_name if hasattr(candidate, 'display_name') else str(candidate)
                    break
            wo.project_display = project or 'Sans projet'

            mtn = False
            for candidate in (
                getattr(mo, 'x_studio_mtn_mrp_sale_order', False) if mo else False,
                getattr(sale, 'x_studio_mtn_mrp_sale_order', False) if sale else False,
                getattr(sale, 'client_order_ref', False) if sale else False,
            ):
                if candidate:
                    mtn = candidate.display_name if hasattr(candidate, 'display_name') else str(candidate)
                    break
            wo.mtn_display = mtn or False

    @api.depends('workcenter_id', 'name', 'operation_id', 'operation_id.sequence')
    def _compute_color_index(self):
        for wo in self:
            rank = wo._fma_rank()
            if rank in COLOR_BY_RANK:
                wo.color_index = COLOR_BY_RANK[rank]
            else:
                wc_id = wo.workcenter_id.id or 0
                wo.color_index = ((wc_id - 1) % 11) + 1 if wc_id else 0

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)
