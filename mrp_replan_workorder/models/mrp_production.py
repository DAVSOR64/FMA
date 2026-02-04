# -*- coding: utf-8 -*-
import logging
import math
from datetime import datetime, timedelta, time

from odoo import models, fields

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # ------------------------------------------------------------
    # PUBLIC ENTRY POINT
    # ------------------------------------------------------------
    def plan_day_based_from_sale(self, sale_order, security_days=None):
        """
        Planifie l'OF en jour entier à partir d'un Sale Order :
        - fin_fab = delivery_date - security_days (jours ouvrés)
        - planification backward sans chevauchement
        - MAJ dates OF (date_start/date_finished)
        - MAJ transfert composants (deadline = début fab, durée 1 jour)
        """
        self.ensure_one()
        # 👇 DEBUG VISUEL DANS LE CHATTER
        self.message_post(body="🧪 DEBUG : planification jour entier exécutée")
        delivery_dt = sale_order.commitment_date
        if not delivery_dt:
            _logger.info("SO %s sans commitment_date : planification ignorée pour MO %s", sale_order.name, self.name)
            return False

        if security_days is None:
            security_days = self._get_security_days_default()

        self._plan_day_based(delivery_dt=delivery_dt, security_days=security_days)
        return True

    # ------------------------------------------------------------
    # CORE SCHEDULING (DAY-BASED)
    # ------------------------------------------------------------
    def _plan_day_based(self, delivery_dt, security_days=6):
        """
        Planification jour entier :
        - end_fab_day = delivery_dt - security_days (jours ouvrés)
        - dernière opération "se termine" end_fab_day (fin de journée)
        - chaque opération occupe N jours ouvrés (N = ceil(durée_h / hours_per_day))
        - opération précédente se termine le jour ouvré précédent le début du bloc suivant
        """
        self.ensure_one()
        
        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel")).sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        if not workorders:
            _logger.info("MO %s : aucune opération (workorder) à planifier", self.name)
            # On met quand même des dates sur l'OF via fin_fab si tu veux, mais ici on ne fait rien.
            return

        delivery_dt = fields.Datetime.to_datetime(delivery_dt)

        # 1) Calcul fin de fabrication (jour ouvré)
        end_fab_dt = self._add_working_days(delivery_dt, -float(security_days))
        end_fab_day = end_fab_dt.date()

        _logger.info("MO %s : delivery=%s | security_days=%s | end_fab_day=%s",
                     self.name, delivery_dt, security_days, end_fab_day)

        # 2) Backward : on part de la dernière opération
        current_end_day = self._previous_or_same_working_day(end_fab_day, workorders[-1].workcenter_id)

        for wo in workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id), reverse=True):
            wc = wo.workcenter_id
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8

            duration_minutes = wo.duration_expected or 0.0
            duration_hours = duration_minutes / 60.0

            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            last_day = self._previous_or_same_working_day(current_end_day, wc)
            first_day = last_day
            for _ in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)

            start_dt = self._morning_dt(first_day, wc)
            end_dt = self._evening_dt(last_day, wc)

            wo.write({
                "date_start": start_dt,
                "date_finished": end_dt,
            })

            _logger.info("  WO %s (%s): %s -> %s | %s min (~%s h) => %s j",
                         wo.name, wc.display_name, first_day, last_day,
                         int(duration_minutes), round(duration_hours, 2), required_days)

            # L'opération précédente doit finir le jour ouvré précédent le début de ce bloc
            current_end_day = self._previous_working_day(first_day, wc)

        # 3) MAJ dates OF = début 1ère op / fin dernière op
        self._update_mo_dates_from_workorders()

        # 4) MAJ picking "Collecter les composants"
        self._update_components_picking_dates()

    # ------------------------------------------------------------
    # PICKING (COLLECT COMPONENTS) DATES
    # ------------------------------------------------------------
    def _update_components_picking_dates(self):
        """
        Le transfert "Collecter les composants" doit être terminé pour le début fab.
        Règle :
        - date_deadline = date_start MO (matin)
        - scheduled_date = jour ouvré précédent (matin) -> durée "1 jour" conceptuellement
        """
        self.ensure_one()
        if not self.date_start:
            return

        start_fab_day = fields.Datetime.to_datetime(self.date_start).date()

        # On cible les pickings liés au MO (souvent origin = nom MO)
        pickings = self.env["stock.picking"].search([
            ("origin", "=", self.name),
            ("state", "not in", ("done", "cancel")),
        ])

        if not pickings:
            _logger.info("MO %s : aucun picking lié (origin=%s) pour MAJ dates composants", self.name, self.name)
            return

        # Si plusieurs pickings, on essaye de filtrer ceux "collecte composants"
        # (à adapter si tu as un picking_type_id spécifique)
        component_pickings = pickings.filtered(
            lambda p: "collect" in (p.picking_type_id.name or "").lower()
            or "compos" in (p.picking_type_id.name or "").lower()
        ) or pickings

        prev_day = self._previous_working_day(start_fab_day, self.workorder_ids[:1].workcenter_id if self.workorder_ids else None)

        scheduled_dt = datetime.combine(prev_day, time(7, 30))
        deadline_dt = datetime.combine(start_fab_day, time(7, 30))

        component_pickings.write({
            "scheduled_date": scheduled_dt,
            "date_deadline": deadline_dt,
        })

        _logger.info("MO %s : pickings(%s) scheduled=%s | deadline=%s",
                     self.name, len(component_pickings), scheduled_dt, deadline_dt)

    # ------------------------------------------------------------
    # HELPERS: company/security days
    # ------------------------------------------------------------
    def _get_security_days_default(self):
        """
        Délai de sécurité par défaut.
        - tu peux changer ce paramètre dans Odoo : Paramètres techniques > Paramètres système
          clé : mrp_replan_workorder.security_days
        """
        val = self.env["ir.config_parameter"].sudo().get_param("mrp_replan_workorder.security_days", default="6")
        try:
            return int(val)
        except Exception:
            return 6

    # ------------------------------------------------------------
    # HELPERS: work calendar (weekend + holidays)
    # ------------------------------------------------------------
    def _add_working_days(self, dt, days):
        """
        Ajoute (ou soustrait) des jours ouvrés via le calendrier société.
        compute_leaves=True -> tient compte des jours fériés/congés.
        """
        cal = self.env.company.resource_calendar_id
        if not cal:
            return dt + timedelta(days=days)

        return cal.plan_days(float(days), dt, compute_leaves=True)

    def _previous_or_same_working_day(self, day, workcenter):
        """
        Retourne day si c'est un jour ouvré (selon calendrier),
        sinon renvoie le jour ouvré précédent.
        """
        if not day:
            return day
    
        # fallback si pas de poste
        if not workcenter:
            d = day
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d
    
        cal = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if not cal:
            d = day
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d
    
        d = day
        for _ in range(365):
            start_dt = datetime.combine(d, time.min)
            end_dt = datetime.combine(d, time.max)
    
            intervals = cal._work_intervals_batch(start_dt, end_dt)
            if intervals.get(False):
                return d
    
            d -= timedelta(days=1)
    
        return day
