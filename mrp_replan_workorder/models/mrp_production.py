import logging
from odoo import models, fields, api
from datetime import timedelta

_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    ir_log_ids = fields.One2many('ir.logging', 'connector_id')


    def button_plan(self):
        _logger.warning("**********dans le module********* %s ")
        res = super().button_plan()

        for production in self:
            date_debut_of = production.date_start
            if not date_debut_of:
                _logger.warning("Pas de date de début sur l'OF %s, on saute", production.name)
                continue
                
            # Trier les workorders par ordre des opérations
            workorders = sorted(production.workorder_ids, key=lambda wo: wo.operation_id.sequence)
            previous_end_date = date_debut_of
            
            for workorder in workorders:
                # Délai inter-opérations selon le poste précédent et le poste actuel
                delay_minutes = 0
                if workorder != workorders[0]:
                    delay_obj = self.env['x_delai_entre_operatio'].search([
                        ('x_studio_poste_de_travail_deb', '=', previous_workorder.workcenter_id.id),
                        ('x_studio_poste_de_travail_fin', '=', workorder.workcenter_id.id)
                    ], limit=1)
                    delay_minutes = delay_obj.x_studio_dlai_entre_oprations if delay_obj else 0
                    _logger.info("Délai entre %s → %s = %s min", previous_workorder.workcenter_id.name, workorder.workcenter_id.name, delay_minutes)

                # Calcul de la date de début
                workorder.date_start = previous_end_date + timedelta(minutes=delay_minutes)

                # Calcul de la date de fin en fonction de la durée attendue
                duration = workorder.duration_expected or 0.0
                workorder.date_finished = workorder.date_start + timedelta(minutes=duration)

                _logger.info("Opération %s : Start = %s / End = %s", workorder.name, workorder.date_start, workorder.date_finished)

                # Sauvegarde du workorder précédent
                previous_end_date = workorder.date_finished
                previous_workorder = workorder

        return res
