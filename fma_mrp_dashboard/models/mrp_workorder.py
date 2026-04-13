# -*- coding: utf-8 -*-
from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    project_display = fields.Char(
        string='Projet',
        compute='_compute_planning_labels',
        store=True,
    )
    mtn_display = fields.Char(
        string='N° MTN',
        compute='_compute_planning_labels',
        store=True,
    )
    color_index = fields.Integer(
        string='Couleur planning',
        compute='_compute_color_index',
        store=True,
    )

    gantt_label = fields.Char(
        string='Label GANTT',
        compute='_compute_gantt_label',
        store=True,
    )

    @api.depends('production_id', 'project_display')
    def _compute_gantt_label(self):
        for wo in self:
            mo_name = wo.production_id.name or ''
            projet = wo.project_display or ''
            if projet and projet != 'Sans projet':
                wo.gantt_label = f"{mo_name} | {projet}"
            else:
                wo.gantt_label = mo_name

    def name_get(self):
        """Surcharge pour afficher OF | Projet dans le GANTT."""
        result = []
        for wo in self:
            mo_name = wo.production_id.name or ''
            projet = wo.project_display or ''
            if projet and projet != 'Sans projet':
                label = f"{mo_name} | {projet}"
            else:
                label = mo_name
            result.append((wo.id, label))
        return result

    def _compute_display_name(self):
        """Surcharge display_name — utilisé par le GANTT Odoo 17 pour les pills."""
        for wo in self:
            mo_name = wo.production_id.name or ''
            projet = wo.project_display or ''
            if projet and projet != 'Sans projet':
                wo.display_name = f"{mo_name} | {projet}"
            else:
                wo.display_name = mo_name or wo.name

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

    @api.depends(
        'macro_planned_start',
        'date_start',
        'date_finished',
        'duration_expected',
    )
    def _compute_gantt_dates(self):
        from datetime import timedelta
        for wo in self:
            # Date de début : macro_planned_start en priorité, sinon date_start
            start = getattr(wo, 'macro_planned_start', False) or wo.date_start
            wo.gantt_date_start = start

            # Date de fin : date_finished en priorité
            stop = wo.date_finished
            # Si pas de fin mais une durée → calculer depuis le début
            if not stop and start and wo.duration_expected:
                stop = start + timedelta(minutes=wo.duration_expected)
            wo.gantt_date_stop = stop

    @api.depends(
        'production_id',
        'production_id.name',
        'production_id.origin',
        'production_id.procurement_group_id',
    )
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


    @api.depends('workcenter_id')
    def _compute_color_index(self):
        """Couleurs métier FMA fixes par poste pour le Gantt."""
        for wo in self:
            name = (wo.workcenter_id.name or '').strip().lower()
            if 'débit' in name or 'debit' in name:
                wo.color_index = 1   # rouge
            elif 'cu' in name:
                wo.color_index = 5   # bleu foncé
            elif 'usinage' in name:
                wo.color_index = 4   # bleu clair
            elif 'montage' in name:
                wo.color_index = 10  # vert
            elif 'vitrage' in name:
                wo.color_index = 11  # violet
            elif 'emballage' in name:
                wo.color_index = 3   # jaune
            else:
                wo.color_index = 0

    def write(self, vals):
        """
        Pas de recalcul automatique du macro planning ici.
        Le recalcul global reste manuel ou via cron.
        """
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        """Pas de refresh global à la création."""
        return super().create(vals_list)
