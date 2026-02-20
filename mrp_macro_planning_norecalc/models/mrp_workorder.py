# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

SEUIL_AUTO_REFRESH = 100


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def write(self, vals):
        """
        Auto-refresh du cache charge si modification des champs critiques
        ET si nombre de workorders actifs <= SEUIL_AUTO_REFRESH
        """
        res = super().write(vals)
        
        # Champs qui impactent la charge
        critical_fields = {'date_start', 'date_planned_finished', 'duration_expected', 
                          'duration', 'state', 'workcenter_id'}
        
        if any(f in vals for f in critical_fields):
            nb_active = self.env['mrp.workorder'].search_count([
                ('state', 'not in', ('done', 'cancel')),
                ('date_start', '!=', False)
            ])
            
            if nb_active <= SEUIL_AUTO_REFRESH:
                _logger.info('AUTO-REFRESH charge : %d workorders actifs', nb_active)
                try:
                    self.env['mrp.workorder.charge.cache'].refresh()
                except Exception as e:
                    _logger.error('Erreur auto-refresh charge : %s', e)
            else:
                _logger.info('AUTO-REFRESH désactivé : %d workorders (seuil=%d)', 
                           nb_active, SEUIL_AUTO_REFRESH)
        
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-refresh après création si sous le seuil"""
        res = super().create(vals_list)
        
        nb_active = self.env['mrp.workorder'].search_count([
            ('state', 'not in', ('done', 'cancel')),
            ('date_start', '!=', False)
        ])
        
        if nb_active <= SEUIL_AUTO_REFRESH:
            _logger.info('AUTO-REFRESH charge après création : %d workorders', nb_active)
            try:
                self.env['mrp.workorder.charge.cache'].refresh()
            except Exception as e:
                _logger.error('Erreur auto-refresh charge : %s', e)
        
        return res
