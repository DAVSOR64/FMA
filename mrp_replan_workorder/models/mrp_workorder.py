# -*- coding: utf-8 -*-
import logging
from odoo import models, api
from datetime import timedelta

_logger = logging.getLogger(__name__)

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"
    
    def write(self, values):
        """
        Surcharge pour replanifier les opérations suivantes du MÊME OF
        si on modifie la date manuellement
        """
        # Sauvegarder les anciennes dates
        old_dates = {
            wo.id: {
                'start': wo.date_start,
                'finished': wo.date_finished
            }
            for wo in self
        }
        
        # Appel standard
        res = super().write(values)
        
        # Détecter si modification de date
        trigger_fields = {'date_start', 'date_finished'}
        if trigger_fields.intersection(values.keys()):
            for workorder in self:
                old = old_dates.get(workorder.id, {})
                
                # Vérifier si vraiment changé
                if (old.get('start') != workorder.date_start or
                    old.get('finished') != workorder.date_finished):
                    
                    _logger.info(
                        "🔄 Modification détectée sur %s (OF %s), replanification des opérations suivantes",
                        workorder.name,
                        workorder.production_id.name
                    )
                    
                    workorder._reschedule_next_operations()
        
        return res
    
    def _reschedule_next_operations(self):
        """
        Recalcule les dates des opérations suivantes DU MÊME OF
        Règle : chaque opération suivante démarre le LENDEMAIN
        """
        self.ensure_one()
        
        # Récupérer les opérations suivantes du MÊME OF
        next_operations = self.env['mrp.workorder'].search([
            ('production_id', '=', self.production_id.id),
            ('sequence', '>', self.sequence),
            ('state', 'not in', ['done', 'cancel'])
        ], order='sequence')
        
        if not next_operations:
            _logger.info("  ℹ️  Aucune opération suivante à replanifier")
            return
        
        _logger.info(
            "  📋 Replanification de %d opération(s) suivante(s)",
            len(next_operations)
        )
        
        # Point de départ = date de l'opération courante
        current_date = (self.date_finished or self.date_start).date()
        
        for operation in next_operations:
            # LENDEMAIN
            next_day = current_date + timedelta(days=1)
            
            # Prochain jour ouvré
            next_working_day = self.production_id._get_next_working_day(
                next_day,
                operation.workcenter_id
            )
            
            # Heure de début
            start_datetime = self.production_id._get_morning_datetime(
                next_working_day,
                operation.workcenter_id
            )
            
            # Fin
            duration_minutes = operation.duration_expected
            end_datetime = start_datetime + timedelta(minutes=duration_minutes)
            
            # Mise à jour SANS déclencher récursion
            super(MrpWorkorder, operation).write({
                'date_start': start_datetime,
                'date_finished': end_datetime,
            })
            
            _logger.info(
                "    ✅ %s replanifié : %s de %s à %s",
                operation.name,
                next_working_day.strftime('%Y-%m-%d'),
                start_datetime.strftime('%H:%M'),
                end_datetime.strftime('%H:%M')
            )
            
            # Préparer pour la prochaine
            current_date = next_working_day
        
        # Mettre à jour l'OF
        self.production_id._update_production_dates()
