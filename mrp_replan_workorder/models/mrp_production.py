# -*- coding: utf-8 -*-
import logging
import math
from datetime import datetime, timedelta, time

import pytz

from odoo import models, fields

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # ============================================================
    # PUBLIC ENTRY POINT
    # ============================================================
    def plan_day_based_from_sale(self, sale_order, security_days=None):
        """
        Planifie l'OF en JOUR ENTIER à partir du Sale Order :
        - fin fab = delivery_date (SO.commitment_date) - security_days (jours ouvrés)
        - backward sans chevauchement (l'op précédente finit la veille ouvrée)
        - écrit dates WO (planned+real si dispo)
        - MAJ dates OF (planned+real si dispo)
        - MAJ picking composants (deadline = début fab, scheduled = veille ouvrée)
        """
        self.ensure_one()

        delivery_dt = sale_order.commitment_date
        if not delivery_dt:
            _logger.info("SO %s sans commitment_date : planif ignorée pour MO %s", sale_order.name, self.name)
            return False

        if security_days is None:
            security_days = self._get_security_days_default()

        self._plan_day_based(delivery_dt=delivery_dt, security_days=int(security_days))
        return True

    # ============================================================
    # CORE SCHEDULING (DAY-BASED, BACKWARD)
    # ============================================================
    def _plan_day_based(self, delivery_dt, security_days=6):
        """
        Planification jour entier, à rebours :
        - end_fab_day = delivery_dt - security_days (jours ouvrés)
        - dernière opération se termine end_fab_day (fin de journée)
        - chaque opération occupe N jours ouvrés (ceil(durée_h / hours_per_day))
        - opération précédente se termine la veille ouvrée du début du bloc suivant
        """
        self.ensure_one()

        # Preuve visuelle que le code passe
        try:
            self.message_post(body="🧪 DEBUG : planification jour entier exécutée")
        except Exception:
            # si chatter non dispo (rare), on ne casse pas
            pass

        # 1) Workorders à planifier (tri robuste)
        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not workorders:
            _logger.info("MO %s : aucun workorder à planifier", self.name)
            return

        # Tri : opération.sequence puis id
        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        delivery_dt = fields.Datetime.to_datetime(delivery_dt)

        # 2) Fin de fabrication = livraison - délai sécurité en jours ouvrés (calendrier société)
        end_fab_dt = self._add_working_days_company(delivery_dt, -float(security_days))
        end_fab_day = end_fab_dt.date()

        _logger.info(
            "MO %s : delivery=%s | security_days=%s | end_fab_day=%s",
            self.name, delivery_dt, security_days, end_fab_day
        )

        # 3) Backward planning
        last_wc = workorders[-1].workcenter_id
        current_end_day = self._previous_or_same_working_day(end_fab_day, last_wc)

        for wo in workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id), reverse=True):
            wc = wo.workcenter_id
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id

            hours_per_day = cal.hours_per_day or 7.8  # fallback si pas renseigné

            duration_minutes = wo.duration_expected or 0.0
            duration_hours = duration_minutes / 60.0

            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            # Bloc de required_days se terminant à current_end_day
            last_day = self._previous_or_same_working_day(current_end_day, wc)
            first_day = last_day
            for _ in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)

            start_dt = self._morning_dt(first_day, wc)
            end_dt = self._evening_dt(last_day, wc)

            self._write_workorder_dates(wo, start_dt, end_dt)

            _logger.info(
                "  WO %s (%s): %s -> %s | %s min (~%s h) => %s j",
                wo.name, wc.display_name, first_day, last_day,
                int(duration_minutes), round(duration_hours, 2), required_days
            )

            # L'opération précédente doit finir la veille ouvrée du début de ce bloc
            current_end_day = self._previous_working_day(first_day, wc)

        # 4) MAJ dates OF depuis les WO (planned + real)
        self._update_mo_dates_from_workorders()

        # 5) MAJ picking composants
        self._update_components_picking_dates()

    # ============================================================
    # WRITE DATES (WO / MO)
    # ============================================================
    def _write_workorder_dates(self, wo, start_dt, end_dt):
        """Écrit planned+real si les champs existent sur mrp.workorder."""
        vals = {}
        if "date_planned_start" in wo._fields:
            vals["date_planned_start"] = start_dt
        if "date_planned_finished" in wo._fields:
            vals["date_planned_finished"] = end_dt
        if "date_start" in wo._fields:
            vals["date_start"] = start_dt
        if "date_finished" in wo._fields:
            vals["date_finished"] = end_dt

        if vals:
            wo.write(vals)
    def _update_mo_dates_from_workorders(self):
        self.ensure_one()
    
        wos = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel") and w.date_start and w.date_finished)
        if not wos:
            return
    
        first_wo = wos.sorted("date_start")[0]
        last_wo = wos.sorted("date_finished")[-1]
    
        self.write({
            "date_start": first_wo.date_start,
            "date_finished": last_wo.date_finished,
            **({"date_deadline": last_wo.date_finished} if "date_deadline" in self._fields else {}),
        })

    # ============================================================
    # PICKING COMPONENTS
    # ============================================================
    def _update_components_picking_dates(self):
        self.ensure_one()
    
        if not self.procurement_group_id:
            _logger.info("MO %s : pas de procurement_group_id, MAJ picking ignorée", self.name)
            return
    
        if not self.date_start:
            _logger.info("MO %s : pas de date_start, MAJ picking ignorée", self.name)
            return
    
        start_fab_day = fields.Datetime.to_datetime(self.date_start).date()
    
        pickings = self.env["stock.picking"].search([
            ("group_id", "=", self.procurement_group_id.id),
            ("state", "not in", ("done", "cancel")),
        ])
    
        if not pickings:
            _logger.info("MO %s : aucun picking trouvé via group_id=%s", self.name, self.procurement_group_id.id)
            return
    
        # On cible le picking "collecte composants" si possible
        comp_pickings = pickings.filtered(
            lambda p: "collect" in (p.picking_type_id.name or "").lower()
            or "compos" in (p.picking_type_id.name or "").lower()
            or "component" in (p.picking_type_id.name or "").lower()
        ) or pickings
    
        # veille ouvrée (on prend le WC de la 1ère WO si dispo, sinon juste veille)
        first_wc = self.workorder_ids[:1].workcenter_id if self.workorder_ids else None
        prev_day = self._previous_working_day(start_fab_day, first_wc) if first_wc else (start_fab_day - timedelta(days=1))
    
        scheduled_dt = datetime.combine(prev_day, time(7, 30))
        deadline_dt = datetime.combine(start_fab_day, time(7, 30))
    
        vals = {}
        if "scheduled_date" in comp_pickings._fields:
            vals["scheduled_date"] = scheduled_dt
        if "date_deadline" in comp_pickings._fields:
            vals["date_deadline"] = deadline_dt
    
        if vals:
            comp_pickings.write(vals)
    
        self.message_post(body=f"🧪 DEBUG picking MAJ: {comp_pickings.mapped('name')} scheduled={scheduled_dt} deadline={deadline_dt}")


    # ============================================================
    # SECURITY DAYS
    # ============================================================
    def _get_security_days_default(self):
        """
        Délai de sécurité par défaut (jours ouvrés).
        Param système (optionnel) : mrp_replan_workorder.security_days
        """
        val = self.env["ir.config_parameter"].sudo().get_param("mrp_replan_workorder.security_days", default="6")
        try:
            return int(val)
        except Exception:
            return 6

    # ============================================================
    # CALENDAR HELPERS (WORKING DAYS) - TZ AWARE
    # ============================================================
    def _user_tz(self):
        return pytz.timezone(self.env.user.tz or "UTC")

    def _to_aware(self, dt_naive):
        """Convertit un datetime naïf en datetime timezone-aware (tz user)."""
        tz = self._user_tz()
        return dt_naive if dt_naive.tzinfo else tz.localize(dt_naive)

    def _add_working_days_company(self, dt, days):
        """
        Ajoute/soustrait des jours ouvrés via le calendrier société.
        """
        cal = self.env.company.resource_calendar_id
        if not cal:
            return dt + timedelta(days=days)
        return cal.plan_days(float(days), dt, compute_leaves=True)

    def _previous_or_same_working_day(self, day, workcenter):
        """
        Retourne day si ouvré (calendrier poste + leaves), sinon jour ouvré précédent.
        """
        if not day:
            return day

        d = day
        if not workcenter:
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        cal = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if not cal:
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        for _ in range(365):
            start_dt = self._to_aware(datetime.combine(d, time.min))
            end_dt = self._to_aware(datetime.combine(d, time.max))
            intervals = cal._work_intervals_batch(start_dt, end_dt)
            if intervals.get(False):
                return d
            d -= timedelta(days=1)

        return day

    def _previous_working_day(self, day, workcenter):
        """
        Jour ouvré précédent (calendrier poste + leaves).
        """
        d = day - timedelta(days=1)
        if not workcenter:
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        cal = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if not cal:
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        for _ in range(365):
            start_dt = self._to_aware(datetime.combine(d, time.min))
            end_dt = self._to_aware(datetime.combine(d, time.max))
            intervals = cal._work_intervals_batch(start_dt, end_dt)
            if intervals.get(False):
                return d
            d -= timedelta(days=1)

        return day - timedelta(days=1)

    def _morning_dt(self, day, workcenter):
        """
        Début de journée selon le calendrier (fallback 07:30).
        """
        start_hour = 7.5
        cal = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if cal and cal.attendance_ids:
            weekday = day.weekday()
            attend = cal.attendance_ids.filtered(lambda a: int(a.dayofweek) == weekday).sorted("hour_from")
            if attend:
                start_hour = attend[0].hour_from

        h = int(start_hour)
        m = int((start_hour - h) * 60)
        return datetime.combine(day, time(h, m))

    def _evening_dt(self, day, workcenter):
        """
        Fin de journée selon le calendrier (fallback 17:00).
        """
        end_hour = 17.0
        cal = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if cal and cal.attendance_ids:
            weekday = day.weekday()
            attend = cal.attendance_ids.filtered(lambda a: int(a.dayofweek) == weekday).sorted("hour_to")
            if attend:
                end_hour = attend[-1].hour_to

        h = int(end_hour)
        m = int((end_hour - h) * 60)
        return datetime.combine(day, time(h, m))
