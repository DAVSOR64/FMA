# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from datetime import datetime, timedelta, time

_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = "mrp.production"
    
    commitment_date = fields.Datetime(
        string="Date de livraison promise",
        help="Date de livraison promise au client"
    )
    
    planning_mode = fields.Selection([
        ('forward', 'Planification avant (depuis date début)'),
        ('backward', 'Planification arrière (depuis date livraison)'),
    ], string='Mode de planification', compute='_compute_planning_mode', store=True)
    
    @api.depends('commitment_date', 'date_planned_start')
    def _compute_planning_mode(self):
        for production in self:
            if production.commitment_date:
                production.planning_mode = 'backward'
            else:
                production.planning_mode = 'forward'
    
    def button_plan(self):
        """
        Surcharge du bouton Plan pour appliquer notre logique :
        - Si date_livraison : planification à REBOURS
        - Sinon : planification AVANT
        - Règle : 1 opération/jour par OF
        - Respect du calendrier (jours fériés, week-ends)
        """
        _logger.info("=" * 80)
        _logger.info("DÉBUT PLANIFICATION PERSONNALISÉE")
        _logger.info("=" * 80)
        
        # Appel du standard AVANT notre logique
        # (important pour les calculs de durée, etc.)
        res = super().button_plan()
        
        for production in self:
            _logger.info("")
            _logger.info("OF : %s (Produit: %s)", production.name, production.product_id.name)
            
            # Vérifier qu'il y a des opérations
            if not production.workorder_ids:
                _logger.warning("  ⚠️  Aucune opération à planifier")
                continue
            
            # Choisir le mode de planification
            if production.commitment_date:
                _logger.info("  📅 Mode : Planification ARRIÈRE (date livraison: %s)", 
                           production.commitment_date.strftime('%Y-%m-%d'))
                production._schedule_backward_from_commitment()
            else:
                _logger.info("  📅 Mode : Planification AVANT (date début: %s)", 
                           (production.date_planned_start or fields.Datetime.now()).strftime('%Y-%m-%d'))
                production._schedule_forward_from_start()
        
        _logger.info("=" * 80)
        _logger.info("FIN PLANIFICATION PERSONNALISÉE")
        _logger.info("=" * 80)
        
        return res
    
    def _schedule_forward_from_start(self):
        """
        Planification AVANT depuis date de début
        Règle : 1 opération/jour, chaque opération le lendemain de la précédente
        """
        self.ensure_one()
        
        start_date = self.date_planned_start
        if not start_date:
            _logger.warning("  ⚠️  Pas de date de début, utilisation de aujourd'hui")
            start_date = fields.Datetime.now()
        
        # Récupérer les workorders triés par séquence
        workorders = self.workorder_ids.filtered(
            lambda w: w.state not in ['done', 'cancel']
        ).sorted('sequence')
        
        _logger.info("  📋 %d opération(s) à planifier", len(workorders))
        
        current_date = start_date.date()
        
        for idx, workorder in enumerate(workorders):
            workcenter = workorder.workcenter_id
            
            # Première opération : commence à la date de l'OF
            if idx == 0:
                planning_date = current_date
            else:
                # Opérations suivantes : LENDEMAIN
                planning_date = current_date + timedelta(days=1)
            
            # Trouver le prochain jour ouvré
            next_working_day = self._get_next_working_day(planning_date, workcenter)
            
            # Heure de début (matin selon calendrier)
            start_datetime = self._get_morning_datetime(next_working_day, workcenter)
            
            # Calculer la fin selon la durée (en MINUTES dans Odoo)
            duration_minutes = workorder.duration_expected
            end_datetime = start_datetime + timedelta(minutes=duration_minutes)
            
            # Mise à jour avec les champs STANDARD
            workorder.write({
                'date_planned_start': start_datetime,
                'date_planned_finished': end_datetime,
            })
            
            _logger.info(
                "  ✅ Op %d/%d : %s sur %s - %s de %s à %s (%.0f min)",
                idx + 1,
                len(workorders),
                workorder.name,
                workcenter.name,
                next_working_day.strftime('%Y-%m-%d (%A)'),
                start_datetime.strftime('%H:%M'),
                end_datetime.strftime('%H:%M'),
                duration_minutes
            )
            
            # Préparer pour la prochaine opération
            current_date = next_working_day
        
        # Mettre à jour les dates de l'OF
        self._update_production_dates()
    
    def _schedule_backward_from_commitment(self):
        """
        Planification ARRIÈRE depuis date de livraison
        On part de la fin et on remonte
        """
        self.ensure_one()
        
        workorders = self.workorder_ids.filtered(
            lambda w: w.state not in ['done', 'cancel']
        ).sorted('sequence', reverse=True)  # INVERSE !
        
        _logger.info("  📋 %d opération(s) à planifier (mode arrière)", len(workorders))
        
        current_date = self.commitment_date.date()
        
        for idx, workorder in enumerate(workorders):
            workcenter = workorder.workcenter_id
            
            # Dernière opération : se termine à la date de livraison
            if idx == 0:
                # Trouver un jour ouvré AVANT la date de livraison
                planning_date = self._get_previous_working_day(current_date, workcenter)
                
                # Fin de journée
                end_datetime = self._get_evening_datetime(planning_date, workcenter)
                
                # Début = fin - durée
                duration_minutes = workorder.duration_expected
                start_datetime = end_datetime - timedelta(minutes=duration_minutes)
                
                # Vérifier que le début ne soit pas avant le matin
                morning = self._get_morning_datetime(planning_date, workcenter)
                if start_datetime < morning:
                    start_datetime = morning
                    # Recalculer la fin si besoin
                    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
            
            else:
                # Opérations précédentes : LA VEILLE de l'opération suivante
                next_wo = workorders[idx - 1]
                next_start_date = next_wo.date_planned_start.date()
                
                # Jour AVANT
                planning_date = next_start_date - timedelta(days=1)
                planning_date = self._get_previous_working_day(planning_date, workcenter)
                
                # Heure de début (matin)
                start_datetime = self._get_morning_datetime(planning_date, workcenter)
                
                # Calculer la fin
                duration_minutes = workorder.duration_expected
                end_datetime = start_datetime + timedelta(minutes=duration_minutes)
            
            # Mise à jour
            workorder.write({
                'date_planned_start': start_datetime,
                'date_planned_finished': end_datetime,
            })
            
            _logger.info(
                "  ✅ Op %d/%d : %s sur %s - %s de %s à %s (%.0f min)",
                len(workorders) - idx,
                len(workorders),
                workorder.name,
                workcenter.name,
                planning_date.strftime('%Y-%m-%d (%A)'),
                start_datetime.strftime('%H:%M'),
                end_datetime.strftime('%H:%M'),
                duration_minutes
            )
            
            # Préparer pour l'opération précédente
            current_date = planning_date
        
        # Mettre à jour les dates de l'OF
        self._update_production_dates()
    
    def _get_next_working_day(self, from_date, workcenter):
        """
        Trouve le prochain jour ouvré APRÈS from_date
        Tient compte du calendrier (jours fériés, week-ends)
        """
        calendar = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        
        if not calendar:
            # Pas de calendrier : sauter juste les week-ends
            current = from_date
            while current.weekday() >= 5:  # 5=samedi, 6=dimanche
                current += timedelta(days=1)
            return current
        
        # Utiliser le calendrier Odoo
        start_dt = datetime.combine(from_date, time.min)
        
        try:
            # plan_days = méthode standard Odoo pour calculer X jours de travail
            next_working = calendar.plan_days(
                1.0,  # 1 jour de travail
                start_dt,
                compute_leaves=True  # Prend en compte les congés/jours fériés
            )
            result = next_working.date() if next_working else from_date
            
            # Log si jour férié sauté
            if result != from_date and (result - from_date).days > 1:
                _logger.debug(
                    "    🗓️  Jour(s) férié(s) sauté(s) : %s → %s",
                    from_date.strftime('%Y-%m-%d'),
                    result.strftime('%Y-%m-%d')
                )
            
            return result
            
        except Exception as e:
            _logger.warning("    ⚠️  Erreur calcul jour ouvré : %s", e)
            return from_date
    
    def _get_previous_working_day(self, from_date, workcenter):
        """
        Trouve le jour ouvré AVANT from_date
        """
        calendar = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        
        if not calendar:
            # Pas de calendrier : sauter les week-ends
            current = from_date
            while current.weekday() >= 5:
                current -= timedelta(days=1)
            return current
        
        # Reculer jour par jour jusqu'à trouver un jour ouvré
        current = from_date - timedelta(days=1)
        max_iterations = 30  # Limite de sécurité
        
        for _ in range(max_iterations):
            # Vérifier si ce jour a des heures de travail
            start_dt = datetime.combine(current, time.min)
            end_dt = datetime.combine(current, time.max)
            
            work_intervals = calendar._work_intervals_batch(start_dt, end_dt)
            
            # S'il y a des intervalles de travail, c'est bon
            if work_intervals.get(False):
                return current
            
            # Sinon, jour précédent
            current -= timedelta(days=1)
        
        _logger.warning("    ⚠️  Impossible de trouver un jour ouvré avant %s", from_date)
        return from_date
    
    def _get_morning_datetime(self, date, workcenter):
        """
        Retourne l'heure de début de journée selon le calendrier
        """
        calendar = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        
        start_hour = 8.0  # Défaut 8h00
        
        if calendar and calendar.attendance_ids:
            weekday = date.weekday()  # 0=lundi, 6=dimanche
            
            # Filtrer les plages horaires du jour
            day_attendances = calendar.attendance_ids.filtered(
                lambda a: int(a.dayofweek) == weekday
            )
            
            if day_attendances:
                # Prendre la première plage
                first_attendance = day_attendances.sorted('hour_from')[0]
                start_hour = first_attendance.hour_from
        
        # Convertir en heures/minutes
        hours = int(start_hour)
        minutes = int((start_hour - hours) * 60)
        
        return datetime.combine(date, time(hours, minutes))
    
    def _get_evening_datetime(self, date, workcenter):
        """
        Retourne l'heure de fin de journée selon le calendrier
        """
        calendar = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        
        end_hour = 17.0  # Défaut 17h00
        
        if calendar and calendar.attendance_ids:
            weekday = date.weekday()
            
            day_attendances = calendar.attendance_ids.filtered(
                lambda a: int(a.dayofweek) == weekday
            )
            
            if day_attendances:
                # Prendre la dernière plage
                last_attendance = day_attendances.sorted('hour_to')[-1]
                end_hour = last_attendance.hour_to
        
        hours = int(end_hour)
        minutes = int((end_hour - hours) * 60)
        
        return datetime.combine(date, time(hours, minutes))
    
    def _update_production_dates(self):
        """
        Met à jour les dates de l'OF :
        - Date début = date début première opération
        - Date fin = date fin dernière opération
        """
        self.ensure_one()
        
        workorders = self.workorder_ids.filtered(
            lambda w: w.state not in ['done', 'cancel']
        )
        
        if not workorders:
            return
        
        first_wo = workorders.sorted('date_planned_start')[0]
        last_wo = workorders.sorted('date_planned_finished')[-1]
        
        self.write({
            'date_planned_start': first_wo.date_planned_start,
            'date_planned_finished': last_wo.date_planned_finished,
        })
        
        _logger.info(
            "  📆 OF mis à jour : %s → %s (durée totale: %d jours)",
            first_wo.date_planned_start.strftime('%Y-%m-%d'),
            last_wo.date_planned_finished.strftime('%Y-%m-%d'),
            (last_wo.date_planned_finished.date() - first_wo.date_planned_start.date()).days + 1
        )
