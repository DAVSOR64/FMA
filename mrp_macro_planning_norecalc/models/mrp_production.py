# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    
def write(self, vals):
    """Intercepte les changements de dates pour recalculer les opérations.

    ⚠️ IMPORTANT:
    - Ne doit JAMAIS s'exécuter lors des actions Planifier/Déprogrammer (button_plan),
      car Odoo écrit des dates intermédiaires (False / recompute) et cela casse le macro-planning.
    """
    # Guards: ne pas interférer avec la planification standard ou nos restaurations
    if self.env.context.get("skip_macro_recalc") or self.env.context.get("in_button_plan") or self.env.context.get("in_button_unplan") or self.env.context.get("from_macro_update"):
        return super().write(vals)

    # Si Odoo remet des dates à False (déprogrammer / planification), ne pas recalculer
    if vals.get("date_planned_start") is False or vals.get("date_planned_finished") is False:
        return super().write(vals)

    res = super().write(vals)

    # Recalcul uniquement quand on modifie explicitement les dates (pas pendant button_plan)
    if ("date_planned_start" in vals) or ("date_planned_finished" in vals):
        for production in self:
            production._recalculate_operations_dates(
                date_start_changed=("date_planned_start" in vals),
                date_end_changed=("date_planned_finished" in vals),
            )

    return res

    def _recalculate_operations_dates(self, date_start_changed=False, date_end_changed=False):
        """
        Recalcule les dates des opérations en fonction des changements de dates de fabrication
        
        Args:
            date_start_changed: True si date_planned_start a été modifiée
            date_end_changed: True si date_planned_finished a été modifiée
        """
        self.ensure_one()
        
        if not self.workorder_ids:
            return
        
        # Vérifier si des opérations sont terminées
        if any(wo.state == 'done' for wo in self.workorder_ids):
            raise UserError(_(
                "Impossible de modifier les dates : certaines opérations sont déjà terminées.\n"
                "Vous devez d'abord annuler les opérations terminées."
            ))
        
        # CAS 1 : Changement de date de DÉBUT et aucune opération commencée
        if date_start_changed:
            if any(wo.state not in ('pending', 'waiting', 'ready') for wo in self.workorder_ids):
                raise UserError(_(
                    "Impossible de modifier la date de début : certaines opérations ont déjà démarré.\n"
                    "Vous ne pouvez modifier que la date de fin de fabrication."
                ))
            
            self._recalculate_all_operations_from_start()
        
        # CAS 2 : Changement de date de FIN et certaines opérations ont débuté
        elif date_end_changed:
            self._recalculate_remaining_operations_from_end()

    def _recalculate_all_operations_from_start(self):
        """
        Recalcule toutes les opérations depuis la date de début
        (utilisé quand date_planned_start change et aucune opération commencée)
        """
        self.ensure_one()
        
        if not self.date_planned_start:
            return
        
        # Trier les opérations par séquence
        workorders = self.workorder_ids.sorted(lambda wo: (wo.operation_id.sequence, wo.id))
        
        current_date = self.date_planned_start
        
        for wo in workorders:
            if not wo.workcenter_id or not wo.duration_expected:
                continue
            
            calendar = wo.workcenter_id.resource_calendar_id
            if not calendar:
                # Pas de calendrier : calcul simple
                wo.macro_date_planned = current_date
                current_date = current_date + timedelta(minutes=wo.duration_expected)
                continue
            
            # Avec calendrier : calculer la fin en tenant compte des jours ouvrés
            try:
                date_start_utc = self._to_utc(current_date)
                
                # Calculer la date de fin en ajoutant la durée en minutes ouvrées
                date_end_utc = calendar.plan_hours(
                    wo.duration_expected / 60.0,  # Convertir minutes en heures
                    date_start_utc,
                    compute_leaves=True
                )
                
                if not date_end_utc:
                    # Fallback si plan_hours échoue
                    date_end_utc = date_start_utc + timedelta(minutes=wo.duration_expected)
                
                # Mettre à jour la date de début de cette opération
                wo.macro_date_planned = current_date
                
                # La prochaine opération commence à la fin de celle-ci
                current_date = self._from_utc(date_end_utc)
                
            except Exception as e:
                _logger.warning("Erreur calcul dates WO %s : %s", wo.id, str(e))
                wo.macro_date_planned = current_date
                current_date = current_date + timedelta(minutes=wo.duration_expected)
        
        # Calculer la date de fin calculée de l'OF
        if workorders:
            last_wo = workorders[-1]
            if last_wo.macro_date_planned and last_wo.duration_expected:
                calendar = last_wo.workcenter_id.resource_calendar_id
                if calendar:
                    try:
                        date_start_utc = self._to_utc(last_wo.macro_date_planned)
                        date_finished_macro = calendar.plan_hours(
                            last_wo.duration_expected / 60.0,
                            date_start_utc,
                            compute_leaves=True
                        )
                        self.date_finished_macro = self._from_utc(date_finished_macro) if date_finished_macro else current_date
                    except:
                        self.date_finished_macro = current_date
                else:
                    self.date_finished_macro = last_wo.macro_date_planned + timedelta(minutes=last_wo.duration_expected)
        
        # Vérifier si dépassement de la date de livraison
        self._check_delivery_date_exceeded()
        
        # Rafraîchir le cache charge
        self._refresh_charge_cache_for_production()

    def _recalculate_remaining_operations_from_end(self):
        """
        Recalcule les opérations NON commencées depuis la date de fin souhaitée
        (utilisé quand date_planned_finished change et certaines opérations ont débuté)
        """
        self.ensure_one()
        
        if not self.date_planned_finished:
            return
        
        # Trier les opérations par séquence
        workorders = self.workorder_ids.sorted(lambda wo: (wo.operation_id.sequence, wo.id))
        
        # Identifier la dernière opération commencée
        last_started_wo = None
        remaining_wos = []
        
        for wo in workorders:
            if wo.state not in ('pending', 'waiting', 'ready'):
                last_started_wo = wo
            else:
                remaining_wos.append(wo)
        
        if not remaining_wos:
            # Toutes les opérations ont démarré, juste mettre à jour date_finished_macro
            if workorders:
                last_wo = workorders[-1]
                if last_wo.macro_date_planned and last_wo.duration_expected:
                    calendar = last_wo.workcenter_id.resource_calendar_id
                    if calendar:
                        try:
                            date_start_utc = self._to_utc(last_wo.macro_date_planned)
                            date_finished_macro = calendar.plan_hours(
                                (last_wo.duration_expected - (last_wo.duration or 0)) / 60.0,
                                date_start_utc,
                                compute_leaves=True
                            )
                            self.date_finished_macro = self._from_utc(date_finished_macro) if date_finished_macro else None
                        except:
                            pass
            self._check_delivery_date_exceeded()
            return
        
        # Déterminer la date de début pour les opérations restantes
        if last_started_wo and last_started_wo.macro_date_planned:
            # Calculer la fin de la dernière opération commencée
            calendar = last_started_wo.workcenter_id.resource_calendar_id
            if calendar:
                try:
                    date_start_utc = self._to_utc(last_started_wo.macro_date_planned)
                    remaining_duration = max(last_started_wo.duration_expected - (last_started_wo.duration or 0), 0)
                    date_end_utc = calendar.plan_hours(
                        remaining_duration / 60.0,
                        date_start_utc,
                        compute_leaves=True
                    )
                    current_date = self._from_utc(date_end_utc) if date_end_utc else last_started_wo.macro_date_planned + timedelta(minutes=remaining_duration)
                except:
                    current_date = last_started_wo.macro_date_planned + timedelta(minutes=last_started_wo.duration_expected)
            else:
                current_date = last_started_wo.macro_date_planned + timedelta(minutes=last_started_wo.duration_expected)
        else:
            # Aucune opération commencée, partir de date_planned_start
            current_date = self.date_planned_start
        
        # Recalculer les opérations restantes
        for wo in remaining_wos:
            if not wo.workcenter_id or not wo.duration_expected:
                continue
            
            calendar = wo.workcenter_id.resource_calendar_id
            if not calendar:
                wo.macro_date_planned = current_date
                current_date = current_date + timedelta(minutes=wo.duration_expected)
                continue
            
            try:
                date_start_utc = self._to_utc(current_date)
                date_end_utc = calendar.plan_hours(
                    wo.duration_expected / 60.0,
                    date_start_utc,
                    compute_leaves=True
                )
                
                wo.macro_date_planned = current_date
                current_date = self._from_utc(date_end_utc) if date_end_utc else current_date + timedelta(minutes=wo.duration_expected)
                
            except Exception as e:
                _logger.warning("Erreur calcul dates WO %s : %s", wo.id, str(e))
                wo.macro_date_planned = current_date
                current_date = current_date + timedelta(minutes=wo.duration_expected)
        
        # Mettre à jour date_finished_macro
        self.date_finished_macro = current_date
        
        # Vérifier si dépassement de la date de livraison
        self._check_delivery_date_exceeded()
        
        # Rafraîchir le cache charge
        self._refresh_charge_cache_for_production()

    def _check_delivery_date_exceeded(self):
        """Vérifie si la date de fin calculée dépasse la date de livraison et affiche une alerte"""
        self.ensure_one()
        
        # Récupérer la date de livraison depuis la commande
        delivery_date = None
        if hasattr(self, 'x_studio_mtn_mrp_sale_order') and self.x_studio_mtn_mrp_sale_order:
            delivery_date = self.x_studio_mtn_mrp_sale_order.commitment_date or self.x_studio_mtn_mrp_sale_order.expected_date
        elif hasattr(self, 'sale_id') and self.sale_id:
            delivery_date = self.sale_id.commitment_date or self.sale_id.expected_date
        
        if delivery_date and self.date_finished_macro:
            if self.date_finished_macro.date() > delivery_date:
                raise ValidationError(_(
                    "⚠️ ALERTE DÉPASSEMENT DATE DE LIVRAISON ⚠️\n\n"
                    "Date de fin calculée : %s\n"
                    "Date de livraison : %s\n"
                    "Retard : %d jours\n\n"
                    "La fabrication se terminera APRÈS la date de livraison promise au client !"
                ) % (
                    self.date_finished_macro.strftime('%d/%m/%Y'),
                    delivery_date.strftime('%d/%m/%Y'),
                    (self.date_finished_macro.date() - delivery_date).days
                ))

    def _refresh_charge_cache_for_production(self):
        """Rafraîchit uniquement le cache charge pour cet OF"""
        # On pourrait optimiser en ne recalculant que les workorders de cet OF
        # Pour l'instant on déclenche un refresh complet (à améliorer si lent)
        try:
            self.env['mrp.workorder.charge.cache'].search([
                ('production_id', '=', self.id)
            ]).unlink()
            
            # Recalculer seulement les workorders de cet OF
            for wo in self.workorder_ids:
                if wo.state not in ('done', 'cancel') and wo.date_start:
                    # Appeler la logique de refresh mais juste pour ce workorder
                    pass  # À implémenter si besoin d'optimisation
        except:
            pass

    def _to_utc(self, dt):
        """Convertit datetime en UTC"""
        if dt is None:
            return dt
        if dt.tzinfo is None:
            import pytz
            return pytz.utc.localize(dt)
        return dt.astimezone(pytz.utc)

    def _from_utc(self, dt):
        """Convertit datetime UTC en datetime naive"""
        if dt is None:
            return dt
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
