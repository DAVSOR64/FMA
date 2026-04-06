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

    @api.depends(
        'production_id',
        'production_id.name',
        'production_id.origin',
        'production_id.sale_id',
        'production_id.sale_id.name',
        'production_id.procurement_group_id',
        'production_id.procurement_group_id.sale_id',
    )
    def _compute_planning_labels(self):
        for wo in self:
            mo = wo.production_id
            sale = getattr(mo, 'sale_id', False) or getattr(getattr(mo, 'procurement_group_id', False), 'sale_id', False)

            project = False
            for candidate in (
                getattr(mo, 'x_studio_projet', False),
                getattr(sale, 'x_studio_projet', False),
                getattr(sale, 'project_id', False) and sale.project_id.display_name,
                getattr(sale, 'analytic_account_id', False) and sale.analytic_account_id.display_name,
                getattr(sale, 'name', False),
                getattr(mo, 'origin', False),
                getattr(mo, 'name', False),
            ):
                if candidate:
                    project = candidate.display_name if hasattr(candidate, 'display_name') else str(candidate)
                    break
            wo.project_display = project or 'Sans projet'

            mtn = False
            for candidate in (
                getattr(mo, 'x_studio_mtn_mrp_sale_order', False),
                getattr(sale, 'x_studio_mtn_mrp_sale_order', False),
                getattr(sale, 'client_order_ref', False),
            ):
                if candidate:
                    mtn = candidate.display_name if hasattr(candidate, 'display_name') else str(candidate)
                    break
            wo.mtn_display = mtn or False

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
