# -*- coding: utf-8 -*-
import logging
import math
from datetime import datetime, timedelta, time, date

import pytz
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

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

    def _get_end_date_field_value(self):
        self.ensure_one()
        return getattr(self, "x_studio_date_de_fin", False) or getattr(self, "x_studio_date_fin", False)

    def _get_active_workorders(self, include_progress=True):
        self.ensure_one()
        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not include_progress:
            workorders = workorders.filtered(lambda w: w.state != "progress")
        return workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

    def _validate_target_end_against_delivery(self, target_end_date):
        self.ensure_one()
        delivery_dt, _sale_order = self._get_macro_target_date()
        if not delivery_dt or not target_end_date:
            return delivery_dt
        delivery_date = delivery_dt.date() if hasattr(delivery_dt, "date") else delivery_dt
        if target_end_date > delivery_date:
            days_late = (target_end_date - delivery_date).days
            raise ValidationError(_(
                "⚠️ BLOCAGE : La date de fin de fabrication dépasse la date de livraison client !\n\n"
                "Date de fin fab :    %s\n"
                "Date de livraison :  %s\n"
                "Retard :             %d jours\n\n"
                "Modifiez la date de fin ou négociez la date de livraison avant de replanifier."
            ) % (
                target_end_date.strftime('%d/%m/%Y'),
                delivery_date.strftime('%d/%m/%Y'),
                days_late,
            ))
        return delivery_dt

    def _compute_backward_plan(self, target_end_date, workorders=None):
        self.ensure_one()
        if not target_end_date:
            return []

        workorders = workorders or self._get_active_workorders()
        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))
        if not workorders:
            return []

        last_wc = workorders[-1].workcenter_id
        current_end_day = self._previous_or_same_working_day(target_end_date, last_wc)
        plan_lines = []

        for wo in workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id), reverse=True):
            wc = wo.workcenter_id
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8
            duration_hours, nb_resources = self._get_effective_duration_hours(wo)
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            last_day = self._previous_or_same_working_day(current_end_day, wc)
            first_day = last_day
            for _i in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)

            start_dt = self._morning_dt(first_day, wc)
            end_dt = self._evening_dt(last_day, wc)
            plan_lines.append({
                'wo': wo,
                'macro_dt': start_dt,
                'start_dt': start_dt,
                'end_dt': end_dt,
                'nb_resources': nb_resources,
                'duration_hours': duration_hours,
                'required_days': required_days,
                'first_day': first_day,
                'last_day': last_day,
            })
            current_end_day = self._previous_working_day(first_day, wc)

        plan_lines.reverse()
        return plan_lines

    def _set_wo_planning_dates_full(self, wo, start_dt, end_dt):
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
            wo.with_context(
                mail_notrack=True,
                skip_shift_chain=True,
                skip_macro_recalc=True,
                allow_wo_clear=True,
            ).write(vals)

    def _write_wo_schedule(self, wo, macro_dt, start_dt, end_dt, nb_resources=1):
        vals = {'macro_planned_start': macro_dt}
        if 'x_nb_resources' in wo._fields:
            vals['x_nb_resources'] = nb_resources
        wo.with_context(
            mail_notrack=True,
            skip_macro_recalc=True,
            skip_shift_chain=True,
            allow_wo_clear=True,
        ).write(vals)
        self._set_wo_planning_dates_full(wo, start_dt, end_dt)
        fields_to_refresh = [fname for fname in [
            'macro_planned_start',
            'date_start',
            'date_finished',
            'date_planned_start',
            'date_planned_finished',
        ] if fname in wo._fields]
        if fields_to_refresh:
            wo.flush_recordset(fields_to_refresh)
            wo.invalidate_recordset(fields_to_refresh)

    def _apply_backward_plan(self, plan_lines, forced_end_dt=None):
        self.ensure_one()
        for line in plan_lines:
            self._write_wo_schedule(
                line['wo'],
                line['macro_dt'],
                line['start_dt'],
                line['end_dt'],
                line['nb_resources'],
            )
        self.flush_recordset()
        self._update_mo_dates_from_macro(forced_end_dt=forced_end_dt)
        self._update_components_picking_dates()
        self._refresh_charge_cache_for_production()
        return True

    def _refresh_charge_cache_for_production(self):
        charge_cache = self.env.get('mrp.workorder.charge.cache')
        if charge_cache:
            charge_cache.refresh()
        capacite_cache = self.env.get('mrp.capacite.cache')
        if capacite_cache:
            capacite_cache.refresh()

    # ============================================================
    # ENTRY POINT FROM SALE ORDER (SO -> MO)
    # ============================================================
    def compute_macro_schedule_from_sale(self, sale_order, security_days=6):
        """Planification standard depuis la commande de vente."""
        self.ensure_one()
        raw_delivery = getattr(sale_order, "so_date_de_livraison_prevu", False) \
            or getattr(sale_order, "x_studio_date_de_livraison_prevu", False) \
            or getattr(sale_order, "commitment_date", False)

        delivery_dt = fields.Datetime.to_datetime(raw_delivery)
        if not delivery_dt:
            _logger.info("SO %s : pas de date prévue de livraison -> pas de macro planning", getattr(sale_order, 'name', self.name))
            return False

        workorders = self._get_active_workorders()
        if not workorders:
            _logger.info("MO %s : aucun WO", self.name)
            return False

        end_fab_dt = self._add_working_days_company(delivery_dt, -float(security_days))
        end_fab_day = end_fab_dt.date()

        self.with_context(skip_macro_recalc=True, mail_notrack=True).write({
            'macro_forced_end': end_fab_dt,
            'x_studio_date_de_fin': end_fab_day,
        })

        plan_lines = self._compute_backward_plan(end_fab_day, workorders=workorders)
        self._apply_backward_plan(plan_lines, forced_end_dt=end_fab_dt)
        return True

    # ============================================================
    # ENTRY POINT FROM REPLANIFIER (date_fin custom -> backward)
    # ============================================================
    def compute_macro_schedule_from_date_fin(self):
        """Replanifie depuis x_studio_date_de_fin."""
        self.ensure_one()
        x_end = self._get_end_date_field_value()
        if not x_end:
            raise UserError(_("La date de fin de fabrication (x_studio_date_de_fin) n'est pas renseignée sur l'OF."))
        x_end = fields.Date.to_date(x_end)

        workorders = self._get_active_workorders()
        if not workorders:
            raise UserError(_("Aucune opération active à replanifier sur cet OF."))

        delivery_dt = self._validate_target_end_against_delivery(x_end)
        last_wc = workorders[-1].workcenter_id
        end_fab_dt = self._evening_dt(x_end, last_wc) if last_wc else datetime.combine(x_end, time(17, 0))

        self.with_context(skip_macro_recalc=True, mail_notrack=True).write({
            'macro_forced_end': end_fab_dt,
            'x_studio_date_de_fin': x_end,
        })

        plan_lines = self._compute_backward_plan(x_end, workorders=workorders)
        self._apply_backward_plan(plan_lines, forced_end_dt=end_fab_dt)
        _logger.info("MO %s : REPLANIFIER terminé | livraison=%s", self.name, delivery_dt)
        return True


    def button_plan(self):
        """
        Phase 2 (clic sur Planifier) :
        - Sauvegarde les macro_planned_start AVANT super().button_plan()
        - Exécute la planif standard Odoo
        - APRÈS le super, restaure les macros
        - Réapplique les vraies dates via apply_macro_to_workorders_dates()
        - Recale OF + transfert composants
        """
        _logger.warning("********** button_plan avec restauration macro **********")

        macro_backup = {}
        end_backup = {}

        for production in self:
            end_backup[production.id] = (
                production.date_deadline
                or production.date_finished
                or getattr(production, "date_planned_finished", False)
            )

            for wo in production.workorder_ids:
                if wo.macro_planned_start:
                    macro_backup[wo.id] = {
                        "macro_planned_start": fields.Datetime.to_datetime(wo.macro_planned_start),
                        "x_nb_resources": getattr(wo, "x_nb_resources", 1) or 1,
                    }

        _logger.info("BUTTON_PLAN : sauvegarde %d macros", len(macro_backup))

        res = super(MrpProduction, self.with_context(
            skip_macro_recalc=True,
            in_button_plan=True,
        )).button_plan()

        for production in self:
            workorders = production.workorder_ids.filtered(
                lambda w: w.state not in ("done", "cancel")
            )

            # 1) restauration des macros uniquement
            for wo in workorders:
                saved = macro_backup.get(wo.id)
                if not saved:
                    continue

                vals = {
                    "macro_planned_start": saved["macro_planned_start"],
                }
                if "x_nb_resources" in wo._fields:
                    vals["x_nb_resources"] = saved["x_nb_resources"]

                wo.with_context(
                    skip_shift_chain=True,
                    skip_macro_recalc=True,
                    mail_notrack=True,
                ).write(vals)

            # 2) réappliquer les vraies dates depuis les macros
            production.with_context(
                skip_macro_recalc=True,
                mail_notrack=True,
            ).apply_macro_to_workorders_dates()

            # 3) recaler l'OF sur les macros, avec fin forcée identique
            forced_end_dt = end_backup.get(production.id)
            production.with_context(
                skip_macro_recalc=True,
                mail_notrack=True,
            )._update_mo_dates_from_macro(forced_end_dt=forced_end_dt)

            # 4) recaler les transferts composants
            production.with_context(
                skip_macro_recalc=True,
                mail_notrack=True,
            )._update_components_picking_dates()

        return res

    def button_unplan(self):
        """Déprogrammation standard + nettoyage de nos macros.

        Important : notre override mrp.workorder.write bloque les writes qui vident
        date_start/date_finished (pour éviter que le plan saute). Lors d'une vraie
        déprogrammation, on autorise explicitement ce comportement.
        """
        # Autoriser la remise à False des dates WO pendant le unplan
        res = super(MrpProduction, self.with_context(allow_wo_clear=True)).button_unplan()

        # Nettoyer nos dates macro (sinon elles "reviennent" au prochain recalcul)
        for mo in self:
            try:
                mo.workorder_ids.with_context(skip_macro_recalc=True, mail_notrack=True).write({
                    "macro_planned_start": False,
                })
            except Exception:
                _logger.exception("Erreur nettoyage macro_planned_start lors de la déprogrammation sur %s", mo.name)

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

            duration_hours, _nb = self._get_effective_duration_hours(wo)
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            start_day = fields.Datetime.to_datetime(wo.macro_planned_start).date()
            last_day = start_day
            for _ in range(required_days - 1):
                last_day = self._next_working_day(last_day, wc)

            start_dt = self._morning_dt(start_day, wc)
            end_dt = self._evening_dt(last_day, wc)

            self._set_wo_planning_dates(wo, start_dt, end_dt)

    def _set_wo_planning_dates(self, wo, start_dt, end_dt):
        self._set_wo_planning_dates_full(wo, start_dt, end_dt)


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
            _logger.info("OF %s : forced_end_dt=%s", self.name, end_dt)
        else:
            # 2) Sinon : fin = max fin WO calculée
            end_candidates = []
            for wo in wos:
                wc = wo.workcenter_id
                cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
                hours_per_day = cal.hours_per_day or 7.8
    
                duration_hours, _nb = self._get_effective_duration_hours(wo)
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
        if "date_planned_start" in self._fields:
            vals["date_planned_start"] = start_dt
        if "date_finished" in self._fields:
            vals["date_finished"] = end_dt
        if "date_planned_finished" in self._fields:
            vals["date_planned_finished"] = end_dt
        if "date_deadline" in self._fields:
            vals["date_deadline"] = end_dt
    
        if vals:
            self.with_context(
                mail_notrack=True,
                from_macro_update=True,
                skip_macro_recalc=True,
            ).write(vals)


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
            self.with_context(mail_notrack=True, from_macro_update=True).write(vals)

    # ============================================================
    # PICKING COMPONENTS UPDATE (via procurement group)
    # ============================================================
    def _update_components_picking_dates(self):
        """
        - scheduled_date = 4 jours ouvrés avant le début fab (matin 07:30)
        - date_deadline  = début fab (matin 07:30)
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

        # Reculer de 4 jours ouvrés depuis le début de fabrication
        transfer_day = start_day
        for _ in range(4):
            transfer_day = self._previous_working_day(transfer_day, first_wc)

        scheduled_dt = datetime.combine(transfer_day, time(7, 30))
        deadline_dt = datetime.combine(start_day, time(7, 30))

        _logger.info(
            "MO %s : transfert composants scheduled=%s deadline=%s (4j ouvrés avant début fab %s)",
            self.name, scheduled_dt, deadline_dt, start_day
        )

        vals = {}
        if "scheduled_date" in comp_pickings._fields:
            vals["scheduled_date"] = scheduled_dt
        if "date_deadline" in comp_pickings._fields:
            vals["date_deadline"] = deadline_dt

        if vals:
            comp_pickings.with_context(mail_notrack=True).write(vals)

    # ============================================================
    # CAPACITY RULES HELPER
    # ============================================================
    def _get_effective_duration_hours(self, wo):
        """
        Retourne (duration_hours_effective, nb_resources) pour un workorder,
        en appliquant les règles de capacité par poste (x_capacite_par_poste).

        Logique :
        - On récupère la durée brute du WO en heures
        - On cherche une règle active sur le workcenter :
            duration_min <= duration_hours < duration_max  (duration_max=0 => illimité)
        - Si trouvée : duration_effective = duration_hours / nb_resources
        - Sinon : durée brute, 1 ressource
        """
        duration_minutes = wo.duration_expected or 0.0
        duration_hours = duration_minutes / 60.0

        wc = wo.workcenter_id
        if not wc or 'x_capacite_par_poste' not in self.env:
            return duration_hours, 1

        # Chercher la règle correspondante
        rules = self.env['x_capacite_par_poste'].search([
            ('x_studio_poste', '=', wc.id),
        ])

        matched_rule = None
        for rule in rules:
            d_min = rule.x_studio_dure_min or 0.0
            d_max = rule.x_studio_dure_max or 0.0
            nb_res = rule.x_studio_nbre_ressources or 1

            if duration_hours >= d_min:
                if d_max == 0.0 or duration_hours < d_max:
                    matched_rule = rule
                    break

        if not matched_rule:
            return duration_hours, 1

        nb_resources = max(1, matched_rule.x_studio_nbre_ressources or 1)
        effective_hours = duration_hours / nb_resources

        _logger.info(
            "WO %s (%s) | durée brute=%.2fh | règle: %.0f-%.0fh => %d ressources | durée effective=%.2fh",
            wo.name, wc.display_name,
            duration_hours,
            matched_rule.x_studio_dure_min, matched_rule.x_studio_dure_max,
            nb_resources, effective_hours
        )

        return effective_hours, nb_resources

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

    # ============================================================
    # AJOUT : RECALCUL AUTO DES DATES LORS DE MODIFICATION DE L'OF
    # ============================================================

    def write(self, vals):
        """Intercepte les changements de dates de l'OF.

        RECALCUL MACRO DÉSACTIVÉ À L'ENREGISTREMENT (correction perf v2).
        Le recalcul se fait désormais :
          - via le bouton « Replanifier » sur le formulaire OF,
          - via le cron 3×/jour (8h, 12h, 18h) mrp_macro_cron_replan_all.

        Seule la synchronisation date_deadline ← x_studio_date_de_fin reste
        immédiate (opération légère, pas de calcul de calendrier).
        """
        # Détecter changement de dates
        date_start_changed = 'date_start' in vals
        date_finished_changed = 'date_finished' in vals or 'date_deadline' in vals
        x_end_changed = ('x_studio_date_fin' in vals or 'x_studio_date_de_fin' in vals)

        x_end_input = None
        if x_end_changed:
            x_end_input = vals.get('x_studio_date_fin') or vals.get('x_studio_date_de_fin')
            try:
                if isinstance(x_end_input, datetime):
                    x_end_input = x_end_input.date()
                elif isinstance(x_end_input, str):
                    x_end_input = fields.Date.to_date(x_end_input)
            except Exception:
                x_end_input = None

        if date_start_changed or date_finished_changed or x_end_changed:
            _logger.debug("MRP PRODUCTION WRITE — OF: %s dates modifiées (recalcul différé)", self.mapped('name'))

        # ── Appel standard ──────────────────────────────────────────────────
        res = super().write(vals)

        # ── Sync légère : date_deadline ← x_studio_date_de_fin ─────────────
        # (pas de recalcul macro ici — sera fait au prochain cron / bouton)
        if x_end_changed                 and not self.env.context.get('skip_macro_recalc')                 and not self.env.context.get('from_macro_update'):
            for production in self:
                try:
                    x_end = x_end_input                         or getattr(production, 'x_studio_date_fin', False)                         or getattr(production, 'x_studio_date_de_fin', False)
                    if not x_end:
                        continue
                    wos = production.workorder_ids.sorted(lambda w: (w.operation_id.sequence, w.id))
                    last_wc = wos[-1].workcenter_id if wos else False
                    end_dt = production._evening_dt(x_end, last_wc) if last_wc                         else datetime.combine(x_end, time(17, 0))
                    production.with_context(
                        skip_macro_recalc=True,
                        from_macro_update=True,
                        mail_notrack=True,
                    ).write({'date_deadline': end_dt, 'date_finished': end_dt})
                except Exception as e:
                    _logger.error("Synchro date_deadline OF %s : %s", production.name, str(e))

        return res

    def action_replanifier(self):
        """Bouton Replanifier : popup si dispo, sinon application directe."""
        self.ensure_one()
        if hasattr(self, 'action_open_replan_preview'):
            return self.action_open_replan_preview()
        self.compute_macro_schedule_from_date_fin()
        return True

    @api.model
    def cron_replan_all_productions(self):
        """Cron 13H et 18H : replanning des OF actifs."""
        import traceback
        _logger.info("%s", "=" * 60)
        _logger.info("CRON REPLAN START")
        _logger.info("%s", "=" * 60)

        productions = self.search([('state', 'not in', ('done', 'cancel'))])
        stats = {'traites': 0, 'ignores_sans_date': 0, 'ignores_sans_wo': 0, 'erreurs': 0}

        for mo in productions:
            try:
                x_end = mo._get_end_date_field_value()
                if not x_end:
                    stats['ignores_sans_date'] += 1
                    continue
                x_end = fields.Date.to_date(x_end)

                active_wos = mo._get_active_workorders()
                if not active_wos:
                    stats['ignores_sans_wo'] += 1
                    continue

                if any(w.state == 'progress' for w in active_wos):
                    eligible_wos = active_wos.filtered(lambda w: w.state not in ('progress', 'done', 'cancel'))
                else:
                    eligible_wos = active_wos

                if not eligible_wos:
                    stats['ignores_sans_wo'] += 1
                    continue

                mo._validate_target_end_against_delivery(x_end)
                last_wc = eligible_wos[-1].workcenter_id
                end_fab_dt = mo._evening_dt(x_end, last_wc) if last_wc else datetime.combine(x_end, time(17, 0))
                plan_lines = mo._compute_backward_plan(x_end, workorders=eligible_wos)
                mo.with_context(skip_macro_recalc=True, mail_notrack=True).write({
                    'macro_forced_end': end_fab_dt,
                    'x_studio_date_de_fin': x_end,
                })
                mo._apply_backward_plan(plan_lines, forced_end_dt=end_fab_dt)
                stats['traites'] += 1
            except Exception as e:
                _logger.error("CRON REPLAN | OF %s : ERREUR %s\n%s", mo.name, str(e), traceback.format_exc())
                stats['erreurs'] += 1

        _logger.info(
            "CRON REPLAN END : %d traités | %d sans date | %d sans WO | %d erreurs",
            stats['traites'], stats['ignores_sans_date'], stats['ignores_sans_wo'], stats['erreurs']
        )
        _logger.info("%s", "=" * 60)

    @api.model
    def action_replan_all_productions(self):
        """Alias maintenu pour compatibilité — appelle cron_replan_all_productions."""
        return self.cron_replan_all_productions()

    def _recalculate_macro_on_date_change(self, date_start_changed=False, date_finished_changed=False):
        """
        Recalcule les macro_planned_start des workorders suite à un changement de dates de l'OF
        
        RÈGLES :
        - Si date_start change et aucune opération commencée → recalcul FORWARD depuis date_start
        - Si date_finished change → recalcul BACKWARD depuis date_finished
        - Respecte l'enchaînement : chaque opération commence le lendemain ouvré de la précédente
        - Alerte si dépassement date de livraison
        """
        self.ensure_one()
        
        _logger.info("=== RECALCUL MACRO OF %s ===", self.name)
        
        workorders = self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel'))
        if not workorders:
            _logger.info("Aucune opération à recalculer")
            return
        
        # Tri par séquence
        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))
        
        # Opérations terminées : on les ignore sans erreur
        done_wos = [wo.name for wo in self.workorder_ids if wo.state == 'done']
        if done_wos:
            _logger.info("Opérations terminées ignorées pour recalcul : %s", ', '.join(done_wos))
            if not workorders:
                return
        
        # CAS 1 : Changement date DÉBUT
        if date_start_changed and not date_finished_changed:
            _logger.info("=== CAS 1 : Changement date DÉBUT ===")
            
            # Si des opérations ont déjà démarré, on bascule en mode backward
            started_wos = [wo.name for wo in workorders if wo.state == 'progress']
            if started_wos:
                _logger.info("Opérations démarrées, recalcul backward : %s", ', '.join(started_wos))
                self._recalculate_macro_backward(workorders)
                self._refresh_charge_cache_for_production()
                return
            
            self._recalculate_macro_forward(workorders)
        
        # CAS 2 : Changement date FIN
        elif date_finished_changed:
            _logger.info("=== CAS 2 : Changement date FIN ===")
            self._recalculate_macro_backward(workorders)
        
        # Rafraîchir le cache charge
        self._refresh_charge_cache_for_production()

    def _recalculate_macro_forward(self, workorders):
        """
        Recalcule FORWARD : depuis date_start de l'OF vers le futur
        Utilisé quand date_start change et aucune opération démarrée
        """
        # Invalider le cache ORM pour être sûr de lire la valeur qui vient d'être écrite
        self.invalidate_recordset(['date_start', 'date_finished', 'date_deadline'])

        if not self.date_start:
            return
        
        current_day = fields.Datetime.to_datetime(self.date_start).date()
        
        _logger.info("RECALCUL FORWARD depuis %s", current_day)
        
        for wo in workorders:
            wc = wo.workcenter_id
            if not wc:
                continue
            
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8
            
            duration_minutes = wo.duration_expected or 0.0
            duration_hours, nb_resources = self._get_effective_duration_hours(wo)
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))
            
            # Début = current_day (matin)
            start_day = self._previous_or_same_working_day(current_day, wc)
            macro_dt = self._morning_dt(start_day, wc)
            
            # Mettre à jour macro_planned_start
            write_vals = {'macro_planned_start': macro_dt}
            if "x_nb_resources" in wo._fields:
                write_vals["x_nb_resources"] = nb_resources
            wo.with_context(skip_macro_recalc=True, mail_notrack=True).write(write_vals)
            
            _logger.info("WO %s : macro=%s | brut=%.0f min | eff=%.2fh | %d j | %d ressource(s)",
                        wo.name, macro_dt, duration_minutes, duration_hours, required_days, nb_resources)
            
            # Prochaine opération commence le lendemain ouvré de la fin de celle-ci
            # Fin = start_day + (required_days - 1) jours ouvrés
            end_day = start_day
            for _ in range(required_days - 1):
                end_day = self._next_working_day(end_day, wc)
            
            current_day = self._next_working_day(end_day, wc)
        
        # Recalculer date_finished de l'OF
        self._update_mo_dates_from_macro()

        # Si les WO n'ont plus de date_start (cas post-déprogrammation),
        # appliquer les macros sur date_start/date_finished pour que le Gantt soit à jour
        wos_without_dates = workorders.filtered(lambda w: not w.date_start)
        if wos_without_dates:
            _logger.info("FORWARD : %d WO sans date_start après déprogrammation -> apply_macro", len(wos_without_dates))
            self.with_context(skip_macro_recalc=True).apply_macro_to_workorders_dates()
        
        # Vérifier dépassement livraison
        self._check_delivery_date_exceeded()

    def _recalculate_macro_backward(self, workorders, end_dt=None):
        """
        Recalcule BACKWARD : depuis date_finished de l'OF vers le passé
        Utilisé quand date_finished change (avec ou sans opérations démarrées)
        """
        # Utiliser la date de fin fournie si elle est imposée,
        # sinon date_deadline en priorité, puis date_finished
        end_dt = end_dt or self.date_deadline or self.date_finished
        if not end_dt:
            return
        
        end_day = fields.Datetime.to_datetime(end_dt).date()
        
        _logger.info("RECALCUL BACKWARD depuis %s", end_day)
        
        # Identifier les opérations NON commencées
        # En Odoo 17 : pending, waiting, ready = pas encore démarré
        # On exclut uniquement done, cancel, et progress (en cours d'exécution)
        not_started_wos = workorders.filtered(lambda w: w.state not in ('done', 'cancel', 'progress'))
        started_wos = workorders.filtered(lambda w: w.state == 'progress')
        
        if not not_started_wos:
            # Toutes commencées : juste recalculer date_finished de l'OF
            _logger.info("Toutes les opérations ont démarré, pas de recalcul macro")
            self._update_mo_dates_from_macro(forced_end_dt=end_dt)
            self._check_delivery_date_exceeded()
            return
        
        # Backward sur les non commencées uniquement
        current_end_day = end_day
        
        # Partir de la dernière opération (reverse)
        for wo in reversed(not_started_wos.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))):
            wc = wo.workcenter_id
            if not wc:
                continue
            
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8
            
            duration_minutes = wo.duration_expected or 0.0
            duration_hours, nb_resources = self._get_effective_duration_hours(wo)
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))
            
            # Fin = current_end_day
            last_day = self._previous_or_same_working_day(current_end_day, wc)
            
            # Début = last_day - (required_days - 1) jours ouvrés
            first_day = last_day
            for _ in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)
            
            macro_dt = self._morning_dt(first_day, wc)
            
            write_vals = {'macro_planned_start': macro_dt}
            if "x_nb_resources" in wo._fields:
                write_vals["x_nb_resources"] = nb_resources
            wo.with_context(skip_macro_recalc=True, mail_notrack=True).write(write_vals)
            
            _logger.info("WO %s : macro=%s | %s -> %s | brut=%.0f min | eff=%.2fh | %d j | %d ressource(s)",
                        wo.name, macro_dt, first_day, last_day, duration_minutes, duration_hours, required_days, nb_resources)
            
            # Opération précédente se termine AVANT first_day.
            # On impose un jour calendaire de "trou" entre opérations,
            # puis la prochaine itération recale sur un jour ouvré du workcenter
            # via _previous_or_same_working_day().
            current_end_day = first_day - timedelta(days=1)
        
        # Recalculer date_start de l'OF + forcer la date de fin demandée
        self._update_mo_dates_from_macro(forced_end_dt=end_dt)
        
        # Vérifier dépassement livraison
        self._check_delivery_date_exceeded()

    def _to_date(self, value):
        """Convertit proprement en date"""
        if not value:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        return fields.Date.to_date(value)


    def _check_delivery_date_exceeded(self):
        """Vérifie si la date de fin métier dépasse la date de livraison"""
        self.ensure_one()

        _logger.warning(
            "[DELIVERY CHECK] START | OF=%s | x_de_fin(raw)=%s | date_finished(raw)=%s",
            self.name, self.x_studio_date_de_fin, self.date_finished
        )

        # Récupérer la commande de vente
        so = False
        if hasattr(self, 'x_studio_mtn_mrp_sale_order') and self.x_studio_mtn_mrp_sale_order:
            so = self.x_studio_mtn_mrp_sale_order
            _logger.warning("[DELIVERY CHECK] SO via x_studio_mtn_mrp_sale_order: %s", so.name)
        elif getattr(self, 'sale_id', False):
            so = self.sale_id
            _logger.warning("[DELIVERY CHECK] SO via sale_id: %s", so.name)
        elif self.procurement_group_id and self.procurement_group_id.sale_id:
            so = self.procurement_group_id.sale_id
            _logger.warning("[DELIVERY CHECK] SO via procurement_group: %s", so.name)

        if not so:
            return

        raw_delivery = getattr(so, "so_date_de_livraison_prevu", False) \
            or getattr(so, "x_studio_date_de_livraison_prevu", False) \
            or so.commitment_date \
            or so.expected_date
        delivery_date = self._to_date(raw_delivery)

        x_end = self._to_date(self.x_studio_date_de_fin)

        _logger.warning(
            "[DELIVERY CHECK] VALUES | OF=%s | delivery(raw)=%s -> %s | x_end(raw)=%s -> %s",
            self.name, raw_delivery, delivery_date, self.x_studio_date_de_fin, x_end
        )

        if not delivery_date or not x_end:
            return

        if x_end > delivery_date:
            days_late = (x_end - delivery_date).days

            _logger.warning(
                "[DELIVERY CHECK] LATE | OF=%s | end=%s > delivery=%s | days=%s",
                self.name, x_end, delivery_date, days_late
            )

            raise ValidationError(_(
                "⚠️ ALERTE DÉPASSEMENT DATE DE LIVRAISON ⚠️\n\n"
                "OF : %s\n"
                "Date de fin planifiée : %s\n"
                "Date de livraison promise : %s\n"
                "Retard : %d jours\n\n"
                "La fabrication se terminera APRÈS la date promise au client !"
            ) % (
                self.name,
                x_end.strftime('%d/%m/%Y'),
                delivery_date.strftime('%d/%m/%Y'),
                days_late
            ))

    def _refresh_charge_cache_for_production(self):
        """Rafraîchit le cache charge pour cet OF"""
        try:
            # Supprimer les entrées de cache de cet OF
            cache_model = self.env.get('mrp.workorder.charge.cache')
            if cache_model:
                cache_model.search([('production_id', '=', self.id)]).unlink()
                
                # Recalculer pour les workorders de cet OF
                for wo in self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')):
                    if wo.macro_planned_start and wo.workcenter_id:
                        # Le cache se mettra à jour automatiquement au prochain refresh global
                        pass
        except Exception as e:
            _logger.warning("Impossible de rafraîchir cache charge : %s", str(e))


    # ============================================================
    # CORRECTION : "Tous fabriquer" → transferts produit fini
    # ============================================================

    def button_produce_all(self):
        """Surcharge du bouton « Tous fabriquer » pour valider aussi les transferts.

        Odoo standard produit l'OF mais ne valide pas automatiquement le transfert
        de produit fini. On force la validation de tous les pickings de sortie
        (type_code = 'outgoing' ou picking_type_id.code = 'outgoing') liés à l'OF
        via le procurement_group.
        """
        res = super().button_produce_all() if hasattr(super(), 'button_produce_all') else self._action_generate_backorder_wizard()

        for production in self:
            try:
                production._validate_output_pickings()
            except Exception as e:
                _logger.error("Erreur validation transferts OF %s : %s", production.name, str(e))

        return res

    def _generate_wo_lines(self):
        """Surcharge pour propager la validation des transferts après production immédiate."""
        res = super()._generate_wo_lines() if hasattr(super(), '_generate_wo_lines') else True
        return res

    def _validate_output_pickings(self):
        """Valide les transferts de produit fini liés à cet OF (state=ready/assigned).

        Recherche via procurement_group_id pour couvrir tous les cas
        (backorder, sous-traitance, etc.).
        """
        self.ensure_one()
        if not self.procurement_group_id:
            return

        # Récupérer tous les pickings liés à ce groupe (hors done/cancel)
        pickings = self.env['stock.picking'].search([
            ('group_id', '=', self.procurement_group_id.id),
            ('state', 'in', ('assigned', 'ready', 'confirmed')),
        ])

        # Filtrer sur les transferts de sortie produit fini (pas les approvisionnements composants)
        output_pickings = pickings.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
            or (p.picking_type_id.name or '').lower() in ('livraison', 'delivery orders', 'receipts produit fini', 'sortie')
        )

        if not output_pickings:
            _logger.info("OF %s : aucun transfert sortie à valider", self.name)
            return

        for picking in output_pickings:
            try:
                if picking.state not in ('done', 'cancel'):
                    # Remplir les quantités faites = quantités demandées si vides
                    for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                        for ml in move.move_line_ids:
                            if not ml.qty_done:
                                ml.qty_done = ml.reserved_qty or ml.product_qty or 0.0
                    picking.with_context(skip_sms=True, skip_backorder=True).button_validate()
                    _logger.info("OF %s : transfert %s validé", self.name, picking.name)
            except Exception as e:
                _logger.error("OF %s : impossible de valider le transfert %s : %s",
                              self.name, picking.name, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Méthodes supplémentaires : réordonnancement FMA + batch + popup replanification
# Toutes dans la même classe MrpProduction pour accès garanti à self.*
# ─────────────────────────────────────────────────────────────────────────────

    # ── Réordonnancement FMA ──────────────────────────────────────────────────
    def _fma_rank(self, wo):
        from .mrp_workorder import ORDER_FMA, _norm
        values = [
            _norm(wo.name),
            _norm(wo.workcenter_id.name),
            _norm(wo.operation_id.name if wo.operation_id else ""),
        ]
        for idx, label in enumerate(ORDER_FMA, start=1):
            if any(_norm(label) in val for val in values):
                return idx
        return 999

    def _get_active_fma_workorders(self):
        self.ensure_one()
        return self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel", "progress")
        )

    def _reset_workorder_dependencies(self, ordered_wos):
        if not ordered_wos:
            return
        fields_map = self.env["mrp.workorder"]._fields
        if "blocked_by_workorder_ids" in fields_map:
            ordered_wos.write({"blocked_by_workorder_ids": [(5, 0, 0)]})
        if "next_work_order_id" in fields_map:
            ordered_wos.write({"next_work_order_id": False})
        if "prev_work_order_id" in fields_map:
            ordered_wos.write({"prev_work_order_id": False})
        previous = False
        for wo in ordered_wos:
            values = {}
            if previous:
                if "blocked_by_workorder_ids" in fields_map:
                    values["blocked_by_workorder_ids"] = [(4, previous.id)]
                if "prev_work_order_id" in fields_map:
                    values["prev_work_order_id"] = previous.id
            if values:
                wo.write(values)
            if previous and "next_work_order_id" in fields_map:
                previous.write({"next_work_order_id": wo.id})
            previous = wo

    def action_resequence_fma(self):
        for production in self:
            active_wos = production._get_active_fma_workorders()
            for wo in active_wos:
                rank = production._fma_rank(wo)
                if rank < 999 and wo.operation_id:
                    wo.operation_id.sequence = rank * 10
            ordered_wos = active_wos.sorted(
                key=lambda wo: ((wo.op_sequence or 0), wo.id)
            )
            production._reset_workorder_dependencies(ordered_wos)
            production.action_replanifier()
        return True

    # ── Batch macro replan ────────────────────────────────────────────────────
    def _get_macro_target_date(self):
        """Retourne (delivery_dt, sale_order) pour le recalcul macro.
        Priorité : so_date_de_livraison_prevu > commitment_date > date_deadline
        """
        self.ensure_one()
        sale_order = False
        if self.procurement_group_id:
            sale_order = self.env['sale.order'].search([
                ('procurement_group_id', '=', self.procurement_group_id.id)
            ], limit=1)
        # Pas de SO → fallback via x_studio_mtn_mrp_sale_order
        if not sale_order:
            sale_order = getattr(self, 'x_studio_mtn_mrp_sale_order', False)

        delivery_dt = False
        if sale_order:
            # Priorité 1 : date de livraison prévue custom (so_date_de_livraison_prevu)
            raw = (
                getattr(sale_order, 'so_date_de_livraison_prevu', False)
                or getattr(sale_order, 'x_studio_date_de_livraison_prevu', False)
            )
            if raw:
                delivery_dt = fields.Datetime.to_datetime(raw)
            # Priorité 2 : commitment_date Odoo
            if not delivery_dt and sale_order.commitment_date:
                delivery_dt = fields.Datetime.to_datetime(sale_order.commitment_date)

        # Priorité 3 : date_deadline de l'OF
        if not delivery_dt and self.date_deadline:
            delivery_dt = fields.Datetime.to_datetime(self.date_deadline)
        # Priorité 4 : date_finished de l'OF
        if not delivery_dt and getattr(self, 'date_finished', False):
            delivery_dt = fields.Datetime.to_datetime(self.date_finished)

        return delivery_dt, sale_order

    def _is_macro_batch_eligible(self):
        self.ensure_one()
        active_wos = self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel")
        )
        if not active_wos:
            return False
        started_wos = active_wos.filtered(
            lambda w: w.state == "progress"
            or bool(w.date_start)
            or bool(w.duration)
            or bool(w.qty_produced)
        )
        return not bool(started_wos)

    @api.model
    def action_batch_recompute_macro_not_started(self, security_days=6):
        productions = self.search([("state", "in", ["confirmed", "progress"])])
        treated = 0
        skipped_started = 0
        skipped_no_target = 0
        errors = []

        for mo in productions:
            try:
                if not mo._is_macro_batch_eligible():
                    skipped_started += 1
                    continue
                delivery_dt, sale_order = mo._get_macro_target_date()
                if not delivery_dt:
                    skipped_no_target += 1
                    continue
                mo.compute_macro_schedule_from_sale(
                    sale_order or mo, security_days=security_days
                )
                treated += 1
            except Exception as e:
                errors.append(f"OF {mo.name} : {e}")
                _logger.exception("Batch replan OF %s", mo.name)

        msg = (
            f"✅ {treated} OF replanifiés | "
            f"⏭ {skipped_started} ignorés (démarrés) | "
            f"⚠️ {skipped_no_target} sans date | "
            f"❌ {len(errors)} erreurs"
        )
        return {
            "treated": treated,
            "skipped_started": skipped_started,
            "skipped_no_target": skipped_no_target,
            "errors": errors,
            "message": msg,
        }


    # ── Popup de prévisualisation replanification ─────────────────────────────

    def action_open_replan_preview(self):
        import json
        self.ensure_one()
        from odoo.exceptions import UserError
        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not workorders:
            raise UserError(_("Aucune opération à recalculer."))

        payload = self._build_replan_preview_payload()
        wiz = self.env["mrp.replan.preview.wizard"].create({
            "production_id": self.id,
            "preview_json": json.dumps(payload, default=str),
            "summary_html": self._render_replan_preview_html(payload),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Prévisualisation replanification"),
            "res_model": "mrp.replan.preview.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_replan_operations(self):
        return self.action_open_replan_preview()

    def _build_replan_preview_payload(self):
        from odoo.exceptions import UserError
        self.ensure_one()

        x_end = self._get_end_date_field_value()
        if not x_end:
            raise UserError(_("La date de fin de fabrication n'est pas renseignée sur l'OF."))
        x_end = fields.Date.to_date(x_end)

        workorders = self._get_active_workorders()
        if not workorders:
            raise UserError(_("Aucune opération active à replanifier."))

        delivery_dt = self._validate_target_end_against_delivery(x_end)
        plan_lines = self._compute_backward_plan(x_end, workorders=workorders)

        def _fmt(dt):
            if not dt:
                return "-"
            if hasattr(dt, 'strftime'):
                return dt.strftime('%d/%m/%Y')
            return str(dt)[:10]

        new_start = plan_lines[0]['start_dt'] if plan_lines else None
        first_wc = plan_lines[0]['wo'].workcenter_id if plan_lines else False
        transfer_day = new_start.date() if new_start else None
        if transfer_day:
            for _i in range(4):
                transfer_day = self._previous_working_day(transfer_day, first_wc)

        purchase_orders = self.env['purchase.order']
        if self.procurement_group_id:
            po_lines = self.env['purchase.order.line'].search([
                ('move_dest_ids.group_id', '=', self.procurement_group_id.id),
            ])
            purchase_orders = po_lines.mapped('order_id')

        po_data = [{
            'name': po.name or '',
            'partner': po.partner_id.display_name or '',
            'date_planned': str(po.date_planned)[:10] if po.date_planned else '',
        } for po in purchase_orders]

        return {
            'production_name': self.display_name or self.name or '',
            'date_fin_fab': _fmt(x_end),
            'date_start': _fmt(new_start),
            'transfer_date': _fmt(datetime.combine(transfer_day, time(7, 30)) if transfer_day else None),
            'date_livraison': _fmt(delivery_dt) if delivery_dt else '-',
            'retard': False,
            'purchase_orders': po_data,
            'operations': [{
                'wo_name': line['wo'].name,
                'workcenter': line['wo'].workcenter_id.display_name or '',
                'start': _fmt(line['start_dt']),
                'end': _fmt(line['end_dt']),
                'days': line['required_days'],
                'hours': round(line['duration_hours'], 2),
            } for line in plan_lines],
        }

    def _render_replan_preview_html(self, payload):
        def _fmt_po_date(dt_str):
            if not dt_str:
                return "-"
            try:
                return str(dt_str)[:10].replace('-', '/').split('/')
                d = str(dt_str)[:10].split('-')
                return f"{d[2]}/{d[1]}/{d[0]}"
            except Exception:
                return str(dt_str)[:10]

        def _fmt_date(dt_str):
            if not dt_str:
                return "-"
            try:
                d = str(dt_str)[:10].split('-')
                return f"{d[2]}/{d[1]}/{d[0]}"
            except Exception:
                return str(dt_str)[:10]

        po_rows = ""
        for po in payload.get("purchase_orders", []):
            po_rows += """
                <tr>
                    <td>{name}</td>
                    <td>{partner}</td>
                    <td>{date_planned}</td>
                </tr>
            """.format(
                name=po.get("name", "") or "",
                partner=po.get("partner", "") or "",
                date_planned=_fmt_date(po.get("date_planned", "")),
            )
        if not po_rows:
            po_rows = '<tr><td colspan="3" style="color:#888">Aucun PO lié</td></tr>'

        retard_html = ""
        if payload.get("retard"):
            retard_html = """
                <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:8px;margin:8px 0">
                    ⚠️ <b>Attention : la fin de fabrication dépasse la date de livraison client !</b>
                </div>
            """

        return """
            <div style="font-size:14px; line-height:2.0">
                <p><b>OF :</b> {production_name}</p>
                <hr/>
                <p><b>🏁 Date de fin fab :</b> <span style="color:#555"><b>{date_fin_fab}</b></span></p>
                <p><b>📅 Début fabrication :</b> <span style="color:#1a7abf;font-size:16px"><b>{date_start}</b></span></p>
                <p><b>🚚 Transfert composants :</b> <span style="color:#1a7abf"><b>{transfer_date}</b></span></p>
                <p><b>📦 Livraison client :</b> <span style="color:{livraison_color}"><b>{date_livraison}</b></span></p>
                {retard_html}
                <br/>
                <b>Commandes d'achat liées</b>
                <table class="table table-sm table-bordered" style="margin-top:8px">
                    <thead style="background:#f5f5f5">
                        <tr><th>N° PO</th><th>Fournisseur</th><th>Date prévue</th></tr>
                    </thead>
                    <tbody>{po_rows}</tbody>
                </table>
            </div>
        """.format(
            production_name=payload.get("production_name", "-") or "-",
            date_fin_fab=payload.get("date_fin_fab", "-") or "-",
            date_start=payload.get("date_start", "-") or "-",
            transfer_date=payload.get("transfer_date", "-") or "-",
            date_livraison=payload.get("date_livraison", "-") or "-",
            livraison_color="#dc3545" if payload.get("retard") else "#28a745",
            retard_html=retard_html,
            po_rows=po_rows,
        )

    def action_apply_replan_preview(self, payload=None):
        self.ensure_one()
        self.compute_macro_schedule_from_date_fin()
        return True

    def _apply_replan_real(self, payload=None):
        return self.action_apply_replan_preview(payload)
