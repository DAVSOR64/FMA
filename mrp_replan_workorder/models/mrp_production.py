
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
    # WRITE OVERRIDE : retrigger macro planning on date change
    # ============================================================
    def write(self, values):
        """
        Si on modifie date_start ou date_finished sur l'OF (hors contexte de skip),
        on recalcule automatiquement les dates macro des WO :
        - date_start changée  => forward planning depuis cette date
        - date_finished changée => backward planning (rétroplanification) depuis cette date
        """
        if self.env.context.get("skip_mo_replan"):
            return super().write(values)

        # Capturer les anciennes valeurs AVANT l'écriture
        old_vals = {}
        if "date_start" in values or "date_finished" in values:
            for mo in self:
                old_vals[mo.id] = {
                    "date_start": fields.Datetime.to_datetime(mo.date_start) if mo.date_start else None,
                    "date_finished": fields.Datetime.to_datetime(mo.date_finished) if mo.date_finished else None,
                }

        res = super().write(values)

        if not old_vals:
            return res

        for mo in self:
            prev = old_vals.get(mo.id, {})
            new_start = fields.Datetime.to_datetime(values.get("date_start")) if "date_start" in values else None
            new_end = fields.Datetime.to_datetime(values.get("date_finished")) if "date_finished" in values else None

            # Priorité : date_finished changée => rétroplanif
            if new_end and new_end != prev.get("date_finished"):
                _logger.info(
                    "MO %s : date_finished changée (%s -> %s) => rétroplanification macro",
                    mo.name, prev.get("date_finished"), new_end
                )
                mo.with_context(skip_mo_replan=True)._replan_macro_backward(new_end)

            # Sinon : date_start changée => forward planif
            elif new_start and new_start != prev.get("date_start"):
                _logger.info(
                    "MO %s : date_start changée (%s -> %s) => forward planification macro",
                    mo.name, prev.get("date_start"), new_start
                )
                mo.with_context(skip_mo_replan=True)._replan_macro_forward(new_start)

        return res

    macro_forced_end = fields.Datetime(
        string="Fin macro forcée",
        copy=False,
        help="Date de fin de fabrication imposée (livraison - délai de sécurité)."
    )
    
    def _log_wo_dates(self, label, workorders):
        _logger.info("=== %s | MO %s | WO count=%s ===", label, self.name, len(workorders))
        for wo in workorders:
            _logger.info(
                "WO %s | state=%s | wc=%s | macro=%s | date_start=%s | date_finished=%s | duration=%s",
                wo.name,
                wo.state,
                wo.workcenter_id.display_name if wo.workcenter_id else None,
                getattr(wo, "macro_planned_start", None),
                wo.date_start,
                wo.date_finished,
                wo.duration_expected,
            )

    # ============================================================
    # ENTRY POINT FROM SALE ORDER (SO -> MO)
    # ============================================================
    def compute_macro_schedule_from_sale(self, sale_order, security_days=6):
        """
        Phase 1 (à la confirmation du devis) :
        - calcule et écrit workorder.macro_planned_start (début macro)
        - recale mrp.production.date_start / date_finished depuis macro_planned_start + durées
        - met à jour le picking composants (deadline = début fab, scheduled = veille ouvrée)
        - NE TOUCHE PAS aux dates standard des WO (date_start/date_finished)
        """
        self.ensure_one()

        delivery_dt = fields.Datetime.to_datetime(sale_order.commitment_date)
        if not delivery_dt:
            _logger.info("SO %s : pas de commitment_date -> pas de macro planning", sale_order.name)
            return False

        self.message_post(body="🧪 DEBUG : macro planning (SO confirm) exécuté")

        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not workorders:
            _logger.info("MO %s : aucun WO", self.name)
            return False

        # Tri robuste : séquence opération puis id
        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        # Fin fabrication = livraison - délai sécurité en jours ouvrés (calendrier société)
        end_fab_dt = self._add_working_days_company(delivery_dt, -float(security_days))
        end_fab_day = end_fab_dt.date()

        self.with_context(mail_notrack=True).write({"macro_forced_end": end_fab_dt,})
        self.with_context(mail_notrack=True).write({"x_studio_date_de_fin": end_fab_day})

        _logger.info("MO %s : delivery=%s security_days=%s end_fab_day=%s",
                     self.name, delivery_dt, security_days, end_fab_day)

        # Planif backward en jours ouvrés => on remplit UNIQUEMENT macro_planned_start
        last_wc = workorders[-1].workcenter_id
        current_end_day = self._previous_or_same_working_day(end_fab_day, last_wc)

        # Backward : dernière -> première
        for wo in workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id), reverse=True):
            wc = wo.workcenter_id
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8

            duration_minutes = wo.duration_expected or 0.0
            duration_hours = duration_minutes / 60.0
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            # Bloc de required_days se terminant à current_end_day
            last_day = self._previous_or_same_working_day(current_end_day, wc)
            first_day = last_day
            for _ in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)

            # macro_planned_start = début du bloc (matin)
            macro_dt = self._morning_dt(first_day, wc)

            if "macro_planned_start" in wo._fields:
                wo.with_context(mail_notrack=True).write({"macro_planned_start": macro_dt})

            _logger.info(
                "WO %s (%s): %s -> %s | %s min (~%s h) => %s j | macro_planned_start=%s",
                wo.name, wc.display_name, first_day, last_day,
                int(duration_minutes), round(duration_hours, 2), required_days, macro_dt
            )

            # Décalage “veille ouvrée” entre opérations
            current_end_day = self._previous_working_day(first_day, wc)

        # ✅ Recaler l'OF depuis les macros WO
        self._update_mo_dates_from_macro(forced_end_dt=end_fab_dt)

        # ✅ Recaler les pickings composants depuis le début fab (MO.date_start)
        self._update_components_picking_dates()

        return True

    # ============================================================
    # BUTTON "PLANIFIER" (MO) -> push macro to WO dates for gantt
    # ============================================================
    def button_plan(self):
        """
        Phase 2 (clic sur Planifier) :
        - exécute la planif standard
        - puis FORCE wo.date_start/date_finished à partir de wo.macro_planned_start
          (pour avoir un Gantt exploitable)
        - puis recale date_start/date_finished de l'OF sur les dates WO
        """
       
        _logger.warning("********** dans le module (macro only) **********")
        res = super().button_plan()
    
        for production in self:
            workorders = sorted(
                production.workorder_ids,
                key=lambda wo: wo.operation_id.sequence if wo.operation_id else 0
            )
    
            previous_end_dt = None
    
            for wo in workorders:
                if not wo.macro_planned_start:
                    _logger.warning("WO %s (%s) : macro_planned_start vide -> skip", wo.name, production.name)
                    continue
    
                macro_start = fields.Datetime.to_datetime(wo.macro_planned_start)
    
                # Règle métier : le lendemain (ouvré) matin après la fin précédente
                if previous_end_dt:
                    prev_day = fields.Datetime.to_datetime(previous_end_dt).date()
    
                    # lendemain calendaire puis on saute aux jours ouvrés (selon ton helper)
                    next_day = production._next_working_day(prev_day, wo.workcenter_id)
                    chain_start = production._morning_dt(next_day, wo.workcenter_id)
    
                    start_dt = max(macro_start, chain_start)
                else:
                    start_dt = macro_start
    
                duration_min = wo.duration_expected or 0.0
                end_dt = start_dt + timedelta(minutes=duration_min)
    
                wo.with_context(skip_shift_chain=True, mail_notrack=True).write({
                    "date_start": start_dt,
                    "date_finished": end_dt,
                })
    
                _logger.info(
                    "WO %s : macro=%s | chain_start=%s | start=%s | end=%s | durée=%s min",
                    wo.name,
                    macro_start,
                    (chain_start if previous_end_dt else None),
                    start_dt,
                    end_dt,
                    duration_min,
                )
    
                previous_end_dt = end_dt
        
        return res

    def apply_macro_to_workorders_dates(self):
        """
        Écrit date_start/date_finished des WO à partir de macro_planned_start + durée (jours ouvrés)
        pour toutes les WO non done/cancel.
        """
        self.ensure_one()

        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not workorders:
            return

        # Tri ordre de fabrication
        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        for wo in workorders:
            if not wo.macro_planned_start:
                continue

            wc = wo.workcenter_id
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8

            duration_minutes = wo.duration_expected or 0.0
            duration_hours = duration_minutes / 60.0
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            start_day = fields.Datetime.to_datetime(wo.macro_planned_start).date()
            last_day = start_day
            for _ in range(required_days - 1):
                last_day = self._next_working_day(last_day, wc)

            start_dt = self._morning_dt(start_day, wc)
            end_dt = self._evening_dt(last_day, wc)

            #vals = {}
            #if "date_start" in wo._fields:
            #    vals["date_start"] = start_dt
            #if "date_finished" in wo._fields:
            #    vals["date_finished"] = end_dt

            #if vals:
            #    wo.with_context(mail_notrack=True).write(vals)
            self._set_wo_planning_dates(wo, start_dt, end_dt)

    def _set_wo_planning_dates(self, wo, start_dt, end_dt):
        vals = {}
        # Champs planifiés (selon version)
        if "date_planned_start" in wo._fields:
            vals["date_planned_start"] = start_dt
        if "date_planned_finished" in wo._fields:
            vals["date_planned_finished"] = end_dt
    
        # Fallback (certaines versions)
        if not vals:
            if "date_start" in wo._fields:
                vals["date_start"] = start_dt
            if "date_finished" in wo._fields:
                vals["date_finished"] = end_dt
    
        if vals:
            wo.with_context(mail_notrack=True).write(vals)


    # ============================================================
    # MO DATES UPDATE (FROM MACRO)
    # ============================================================
    def _update_mo_dates_from_macro(self, forced_end_dt=None):
        """
        Recale l'OF sur :
        - début = min(WO.macro_planned_start)
        - fin = forced_end_dt si fourni, sinon fin calculée depuis les WO
        """
        self.ensure_one()
    
        wos = self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel") and w.macro_planned_start
        )
        if not wos:
            return
    
        start_dt = min(wos.mapped("macro_planned_start"))
    
        # 1) Fin forcée = livraison - délai sécurité (jours ouvrés société)
        if forced_end_dt:
            end_dt = fields.Datetime.to_datetime(forced_end_dt)
        else:
            # 2) Sinon : fin = max fin WO calculée
            end_candidates = []
            for wo in wos:
                wc = wo.workcenter_id
                cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
                hours_per_day = cal.hours_per_day or 7.8
    
                duration_minutes = wo.duration_expected or 0.0
                duration_hours = duration_minutes / 60.0
                required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))
    
                start_day = fields.Datetime.to_datetime(wo.macro_planned_start).date()
                last_day = start_day
                for _ in range(required_days - 1):
                    last_day = self._next_working_day(last_day, wc)
    
                end_candidates.append(self._evening_dt(last_day, wc))
    
            end_dt = max(end_candidates) if end_candidates else start_dt
    
        vals = {}
        if "date_start" in self._fields:
            vals["date_start"] = start_dt
        if "date_finished" in self._fields:
            vals["date_finished"] = end_dt
        if "date_deadline" in self._fields:
            vals["date_deadline"] = end_dt
    
        if vals:
            self.with_context(mail_notrack=True).write(vals)


    # ============================================================
    # MO DATES UPDATE (FROM WO DATES)
    # ============================================================
    def _update_mo_dates_from_workorders_dates_only(self):
        """
        Après button_plan (où on écrit date_start/date_finished des WO),
        on recale les dates de l'OF sur les WO.
        """
        self.ensure_one()

        wos = self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel") and w.date_start and w.date_finished
        )
        if not wos:
            return

        first_wo = wos.sorted("date_start")[0]
        last_wo = wos.sorted("date_finished")[-1]

        vals = {}
        if "date_start" in self._fields:
            vals["date_start"] = first_wo.date_start
        if "date_finished" in self._fields:
            vals["date_finished"] = last_wo.date_finished
        if "date_deadline" in self._fields:
            vals["date_deadline"] = last_wo.date_finished

        if vals:
            self.with_context(mail_notrack=True).write(vals)

    # ============================================================
    # PICKING COMPONENTS UPDATE (via procurement group)
    # ============================================================
    def _update_components_picking_dates(self):
        """
        - date_deadline = début fab (MO.date_start, matin)
        - scheduled_date = veille ouvrée (matin)
        Recherche pickings via group_id (procurement group) => robuste.
        """
        self.ensure_one()

        if not self.procurement_group_id:
            _logger.info("MO %s : pas de procurement_group_id, MAJ picking ignorée", self.name)
            return

        if not self.date_start:
            _logger.info("MO %s : pas de date_start, MAJ picking ignorée", self.name)
            return

        start_day = fields.Datetime.to_datetime(self.date_start).date()

        pickings = self.env["stock.picking"].search([
            ("group_id", "=", self.procurement_group_id.id),
            ("state", "not in", ("done", "cancel")),
        ])
        if not pickings:
            _logger.info("MO %s : aucun picking via group_id=%s", self.name, self.procurement_group_id.id)
            return

        comp_pickings = pickings.filtered(
            lambda p: "collect" in (p.picking_type_id.name or "").lower()
            or "compos" in (p.picking_type_id.name or "").lower()
            or "component" in (p.picking_type_id.name or "").lower()
        ) or pickings

        first_wc = self.workorder_ids[:1].workcenter_id if self.workorder_ids else None
        prev_day = self._previous_working_day(start_day, first_wc) if first_wc else (start_day - timedelta(days=1))

        scheduled_dt = datetime.combine(prev_day, time(7, 30))
        deadline_dt = datetime.combine(start_day, time(7, 30))

        vals = {}
        if "scheduled_date" in comp_pickings._fields:
            vals["scheduled_date"] = scheduled_dt
        if "date_deadline" in comp_pickings._fields:
            vals["date_deadline"] = deadline_dt

        if vals:
            comp_pickings.with_context(mail_notrack=True).write(vals)

        self.message_post(
            body=f"🧪 DEBUG : pickings MAJ ({len(comp_pickings)}) scheduled={scheduled_dt} deadline={deadline_dt}"
        )

    # ============================================================
    # REPLAN MACRO : FORWARD (depuis date_start OF)
    # ============================================================
    def _replan_macro_forward(self, start_dt):
        """
        Recalcule macro_planned_start de chaque WO en forward planning
        depuis start_dt (nouvelle date_start de l'OF).
        Recalcule ensuite date_finished de l'OF depuis la fin de la dernière WO.
        Règle métier : même logique que compute_macro_schedule_from_sale mais en avant.
        """
        self.ensure_one()

        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not workorders:
            _logger.info("MO %s : aucun WO -> skip forward replan", self.name)
            return

        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        start_day = fields.Datetime.to_datetime(start_dt).date()
        current_start_day = start_day

        for wo in workorders:
            wc = wo.workcenter_id
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8

            duration_minutes = wo.duration_expected or 0.0
            duration_hours = duration_minutes / 60.0
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            first_day = self._next_or_same_working_day(current_start_day, wc)
            last_day = first_day
            for _ in range(required_days - 1):
                last_day = self._next_working_day(last_day, wc)

            macro_dt = self._morning_dt(first_day, wc)

            if "macro_planned_start" in wo._fields:
                wo.with_context(mail_notrack=True).write({"macro_planned_start": macro_dt})

            _logger.info(
                "FORWARD | WO %s (%s): start=%s end=%s | %s j | macro=%s",
                wo.name, wc.display_name if wc else "?",
                first_day, last_day, required_days, macro_dt
            )

            # Prochain WO commence le lendemain ouvré après la fin de celui-ci
            current_start_day = self._next_working_day(last_day, wc)

        # Recalcule date_finished OF = fin de la dernière WO
        last_wo = workorders[-1]
        wc = last_wo.workcenter_id
        cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
        hours_per_day = cal.hours_per_day or 7.8
        duration_hours = (last_wo.duration_expected or 0.0) / 60.0
        required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

        macro_start_day = fields.Datetime.to_datetime(last_wo.macro_planned_start).date()
        last_day = macro_start_day
        for _ in range(required_days - 1):
            last_day = self._next_working_day(last_day, wc)

        end_fab_dt = self._evening_dt(last_day, wc)

        self.with_context(skip_mo_replan=True, mail_notrack=True).write({
            "date_finished": end_fab_dt,
            "date_deadline": end_fab_dt,
            "macro_forced_end": end_fab_dt,
            "x_studio_date_de_fin": end_fab_dt.date(),
        })

        _logger.info("MO %s : forward replan done | date_start=%s | date_finished=%s", self.name, start_dt, end_fab_dt)
        self.message_post(body=f"📅 Replanification forward : début {start_dt.date()} → fin calculée {end_fab_dt.date()}")

    # ============================================================
    # REPLAN MACRO : BACKWARD (depuis date_finished OF)
    # ============================================================
    def _replan_macro_backward(self, end_dt):
        """
        Recalcule macro_planned_start de chaque WO en rétroplanification
        depuis end_dt (nouvelle date_finished de l'OF).
        Recalcule ensuite date_start de l'OF depuis le début de la première WO.
        Même logique que compute_macro_schedule_from_sale.
        """
        self.ensure_one()

        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not workorders:
            _logger.info("MO %s : aucun WO -> skip backward replan", self.name)
            return

        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        end_fab_day = fields.Datetime.to_datetime(end_dt).date()

        self.with_context(skip_mo_replan=True, mail_notrack=True).write({
            "macro_forced_end": end_dt,
            "x_studio_date_de_fin": end_fab_day,
        })

        last_wc = workorders[-1].workcenter_id
        current_end_day = self._previous_or_same_working_day(end_fab_day, last_wc)

        # Backward : dernière -> première
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

            macro_dt = self._morning_dt(first_day, wc)

            if "macro_planned_start" in wo._fields:
                wo.with_context(mail_notrack=True).write({"macro_planned_start": macro_dt})

            _logger.info(
                "BACKWARD | WO %s (%s): start=%s end=%s | %s j | macro=%s",
                wo.name, wc.display_name if wc else "?",
                first_day, last_day, required_days, macro_dt
            )

            current_end_day = self._previous_working_day(first_day, wc)

        # Recalcule date_start OF = début de la première WO
        first_wo = workorders[0]
        start_fab_dt = fields.Datetime.to_datetime(first_wo.macro_planned_start) if first_wo.macro_planned_start else None

        if start_fab_dt:
            self.with_context(skip_mo_replan=True, mail_notrack=True).write({
                "date_start": start_fab_dt,
            })

        _logger.info("MO %s : backward replan done | date_start=%s | date_finished=%s", self.name, start_fab_dt, end_dt)
        self.message_post(body=f"📅 Rétroplanification : fin imposée {end_fab_day} → début calculé {start_fab_dt.date() if start_fab_dt else '?'}")

    # ============================================================
    # HELPER : prochain jour ouvré ou même jour si ouvré
    # ============================================================
    def _next_or_same_working_day(self, day, workcenter):
        if not day:
            return day

        d = day
        if not workcenter:
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

        cal = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if not cal:
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

        for _ in range(365):
            start_dt = self._to_aware(datetime.combine(d, time.min))
            end_dt = self._to_aware(datetime.combine(d, time.max))
            intervals = cal._work_intervals_batch(start_dt, end_dt)
            if intervals.get(False):
                return d
            d += timedelta(days=1)

        return day

    # ============================================================
    # WORKING DAYS / CALENDAR HELPERS
    # ============================================================
    def _user_tz(self):
        return pytz.timezone(self.env.user.tz or "UTC")

    def _to_aware(self, dt_naive):
        tz = self._user_tz()
        return dt_naive if dt_naive.tzinfo else tz.localize(dt_naive)

    def _add_working_days_company(self, dt, days):
        cal = self.env.company.resource_calendar_id
        if not cal:
            return dt + timedelta(days=days)
        return cal.plan_days(float(days), dt, compute_leaves=True)

    def _previous_or_same_working_day(self, day, workcenter):
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

    def _next_working_day(self, day, workcenter):
        d = day + timedelta(days=1)

        if not workcenter:
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

        cal = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if not cal:
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

        for _ in range(365):
            start_dt = self._to_aware(datetime.combine(d, time.min))
            end_dt = self._to_aware(datetime.combine(d, time.max))
            intervals = cal._work_intervals_batch(start_dt, end_dt)
            if intervals.get(False):
                return d
            d += timedelta(days=1)

        return day + timedelta(days=1)

    def _morning_dt(self, day, workcenter):
        start_hour = 7.5  # fallback 07:30
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
        end_hour = 17.0  # fallback 17:00
        cal = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if cal and cal.attendance_ids:
            weekday = day.weekday()
            attend = cal.attendance_ids.filtered(lambda a: int(a.dayofweek) == weekday).sorted("hour_to")
            if attend:
                end_hour = attend[-1].hour_to

        h = int(end_hour)
        m = int((end_hour - h) * 60)
        return datetime.combine(day, time(h, m))
