
# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models


class MrpCapacityRecomputeMixin(models.AbstractModel):
    _name = 'mrp.capacity.recompute.mixin'
    _description = 'Mixin de recalcul capacité'

    def _trigger_capacity_refresh(self):
        if 'mrp.capacity.week' not in self.env:
            return
        today = fields.Date.today()
        date_from = today - timedelta(days=today.weekday())
        date_to = date_from + timedelta(weeks=52)
        self.env['mrp.capacity.week'].sudo().recompute_range(date_from=date_from, date_to=date_to)
        if 'mrp.capacite.cache' in self.env:
            self.env['mrp.capacite.cache'].sudo().refresh_all(date_from=date_from, date_to=date_to)


class HrLeave(models.Model):
    _inherit = ['hr.leave', 'mrp.capacity.recompute.mixin']

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._trigger_capacity_refresh()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._trigger_capacity_refresh()
        return res

    def unlink(self):
        res = super().unlink()
        self._trigger_capacity_refresh()
        return res


class ResourceCalendarLeaves(models.Model):
    _inherit = ['resource.calendar.leaves', 'mrp.capacity.recompute.mixin']

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._trigger_capacity_refresh()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._trigger_capacity_refresh()
        return res

    def unlink(self):
        res = super().unlink()
        self._trigger_capacity_refresh()
        return res
