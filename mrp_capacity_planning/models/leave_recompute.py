# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models


def _trigger_capacity_refresh(env):
    if 'mrp.capacity.week' not in env:
        return

    today = fields.Date.today()
    date_from = today - timedelta(days=today.weekday())
    date_to = date_from + timedelta(weeks=52)

    env['mrp.capacity.week'].sudo().recompute_range(
        date_from=date_from,
        date_to=date_to,
    )

    if 'mrp.capacite.cache' in env:
        env['mrp.capacite.cache'].sudo().refresh_all(
            date_from=date_from,
            date_to=date_to,
        )


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _trigger_capacity_refresh(self.env)
        return records

    def write(self, vals):
        res = super().write(vals)
        _trigger_capacity_refresh(self.env)
        return res

    def unlink(self):
        res = super().unlink()
        _trigger_capacity_refresh(self.env)
        return res


class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _trigger_capacity_refresh(self.env)
        return records

    def write(self, vals):
        res = super().write(vals)
        _trigger_capacity_refresh(self.env)
        return res

    def unlink(self):
        res = super().unlink()
        _trigger_capacity_refresh(self.env)
        return res
