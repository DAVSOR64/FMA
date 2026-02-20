# -*- coding: utf-8 -*-
import logging
import math
from datetime import datetime, timedelta, time

import pytz
from odoo import models, fields, _
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

            # Décalage "veille ouvrée" entre opérations
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
        - Sauvegarde les macro_planned_start AVANT super().button_plan()
          car Odoo les écrase avec son propre calcul de charge
        - Exécute la planif standard (nécessaire pour changer l'état des WO)
        - Restaure les macro_planned_start sauvegardés
        - Force date_start/date_finished des WO depuis les macros
        - Recale les dates de l'OF
        """
        _logger.warning("********** dans le module (macro only) **********")

        # ── 1. Sauvegarder les macro_planned_start AVANT le super() ──
        macro_backup = {}
        for production in self:
            for wo in production.workorder_ids:
                if wo.macro_planned_start:
                    macro_backup[wo.id] = fields.Datetime.to_datetime(wo.macro_planned_start)

        _logger.info("BUTTON_PLAN : sauvegarde %d macro_planned_start", len(macro_backup))

        # ── 2. Planif standard Odoo (change états WO, vérifie dispo, etc.) ──
        res = super().button_plan()

        # ── 3. Restaurer les macro_planned_start et appliquer sur date_start/date_finished ──
        for production in self.with_context(in_button_plan=True, skip_macro_recalc=True):
            workorders = sorted(
                production.workorder_ids,
                key=lambda wo: wo.operation_id.sequence if wo.operation_id else 0
            )

            for wo in workorders:
                saved_macro = macro_backup.get(wo.id)
                if not saved_macro:
                    _logger.warning("WO %s (%s) : macro_planned_start non sauvegardé -> skip", wo.name, production.name)
                    continue

                # Restaurer macro_planned_start si Odoo l'a écrasé
                if fields.Datetime.to_datetime(wo.macro_planned_start) != saved_macro:
                    _logger.info("WO %s : restauration macro %s -> %s", wo.name, wo.macro_planned_start, saved_macro)
                    wo.with_context(skip_macro_recalc=True, mail_notrack=True).write({
                        "macro_planned_start": saved_macro,
                    })

                # Appliquer macro sur date_start/date_finished
                duration_min = wo.duration_expected or 0.0
                end_dt = saved_macro + timedelta(minutes=duration_min)

                wo.with_context(skip_shift_chain=True, mail_notrack=True).write({
                    "date_start": saved_macro,
                    "date_finished": end_dt,
                })

                _logger.info(
                    "WO %s : macro=%s | start=%s | end=%s | durée=%s min",
                    wo.name, saved_macro, saved_macro, end_dt, duration_min,
                )

            # ── 4. Recaler les dates de l'OF sur les macros WO ──
            production.with_context(
                skip_macro_recalc=True,
                from_macro_update=True,
                mail_notrack=True,
            )._update_mo_dates_from_macro(
                forced_end_dt=production.macro_forced_end or None
            )

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
            # skip_shift_chain : évite que le write WO déclenche _shift_workorders_after
            # skip_macro_recalc : évite un recalcul macro en boucle
            wo.with_context(mail_notrack=True, skip_shift_chain=True, skip_macro_recalc=True).write(vals)


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
        """Intercepte les changements de dates de l'OF pour recalculer les opérations"""
        
        # Détecter changement de dates
        date_start_changed = 'date_start' in vals
        date_finished_changed = 'date_finished' in vals or 'date_deadline' in vals
        
        # Log pour debug
        if date_start_changed or date_finished_changed:
            _logger.info("=== MRP PRODUCTION WRITE === OF: %s, vals: %s", 
                        self.mapped('name'), vals)
        
        # Appel standard
        res = super().write(vals)
        
        # Si changement de dates ET que ce n'est pas un appel interne ET pas depuis _update_mo_dates_from_macro ET pas pendant button_plan
        if (date_start_changed or date_finished_changed) \
           and not self.env.context.get('skip_macro_recalc') \
           and not self.env.context.get('from_macro_update') \
           and not self.env.context.get('in_button_plan'):
            for production in self:
                try:
                    production._recalculate_macro_on_date_change(
                        date_start_changed=date_start_changed,
                        date_finished_changed=date_finished_changed
                    )
                except (UserError, ValidationError) as e:
                    raise
                except Exception as e:
                    _logger.error("Erreur recalcul macro OF %s : %s", production.name, str(e), exc_info=True)
        
        return res

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
        
        # Vérifier si des opérations sont terminées
        done_wos = [wo.name for wo in self.workorder_ids if wo.state == 'done']
        if done_wos:
            raise UserError(_(
                "Impossible de modifier les dates : certaines opérations sont terminées.\n"
                "Opérations terminées : %s"
            ) % ', '.join(done_wos))
        
        # CAS 1 : Changement date DÉBUT
        if date_start_changed and not date_finished_changed:
            _logger.info("=== CAS 1 : Changement date DÉBUT ===")
            
            # Vérifier qu'aucune opération n'a démarré
            started_wos = [wo.name for wo in workorders if wo.state not in ('pending', 'waiting', 'ready')]
            if started_wos:
                raise UserError(_(
                    "Impossible de modifier la date de début : certaines opérations ont déjà démarré.\n"
                    "Opérations démarrées : %s\n"
                    "Vous ne pouvez modifier que la date de fin."
                ) % ', '.join(started_wos))
            
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
            duration_hours = duration_minutes / 60.0
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))
            
            # Début = current_day (matin)
            start_day = self._previous_or_same_working_day(current_day, wc)
            macro_dt = self._morning_dt(start_day, wc)
            
            # Mettre à jour macro_planned_start
            wo.with_context(skip_macro_recalc=True, mail_notrack=True).write({
                'macro_planned_start': macro_dt
            })
            
            _logger.info("WO %s : macro=%s | durée=%s min (~%s j)", 
                        wo.name, macro_dt, duration_minutes, required_days)
            
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

    def _recalculate_macro_backward(self, workorders):
        """
        Recalcule BACKWARD : depuis date_finished de l'OF vers le passé
        Utilisé quand date_finished change (avec ou sans opérations démarrées)
        """
        # Utiliser date_deadline en priorité, sinon date_finished
        end_dt = self.date_deadline or self.date_finished
        if not end_dt:
            return
        
        end_day = fields.Datetime.to_datetime(end_dt).date()
        
        _logger.info("RECALCUL BACKWARD depuis %s", end_day)
        
        # Identifier les opérations NON commencées
        not_started_wos = workorders.filtered(lambda w: w.state in ('pending', 'waiting', 'ready'))
        started_wos = workorders.filtered(lambda w: w.state not in ('pending', 'waiting', 'ready'))
        
        if not not_started_wos:
            # Toutes commencées : juste recalculer date_finished de l'OF
            _logger.info("Toutes les opérations ont démarré, pas de recalcul macro")
            self._update_mo_dates_from_macro()
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
            duration_hours = duration_minutes / 60.0
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))
            
            # Fin = current_end_day
            last_day = self._previous_or_same_working_day(current_end_day, wc)
            
            # Début = last_day - (required_days - 1) jours ouvrés
            first_day = last_day
            for _ in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)
            
            macro_dt = self._morning_dt(first_day, wc)
            
            wo.with_context(skip_macro_recalc=True, mail_notrack=True).write({
                'macro_planned_start': macro_dt
            })
            
            _logger.info("WO %s : macro=%s | %s -> %s | durée=%s min", 
                        wo.name, macro_dt, first_day, last_day, duration_minutes)
            
            # Opération précédente se termine la veille ouvrée
            current_end_day = self._previous_working_day(first_day, wc)
        
        # Recalculer date_start de l'OF
        self._update_mo_dates_from_macro()
        
        # Vérifier dépassement livraison
        self._check_delivery_date_exceeded()

    def _check_delivery_date_exceeded(self):
        """Vérifie si la date de fin calculée dépasse la date de livraison"""
        self.ensure_one()
        
        # Récupérer la date de livraison depuis la commande
        delivery_date = None
        
        # Essayer différents champs selon la config
        if hasattr(self, 'x_studio_mtn_mrp_sale_order') and self.x_studio_mtn_mrp_sale_order:
            so = self.x_studio_mtn_mrp_sale_order
        elif hasattr(self, 'sale_id') and self.sale_id:
            so = self.sale_id
        else:
            # Chercher via procurement group
            if self.procurement_group_id and self.procurement_group_id.sale_id:
                so = self.procurement_group_id.sale_id
            else:
                return
        
        delivery_date = so.commitment_date or so.expected_date
        
        if delivery_date and self.date_finished:
            date_finished = fields.Datetime.to_datetime(self.date_finished).date()
            
            # Assurer que delivery_date est aussi une date
            if isinstance(delivery_date, datetime):
                delivery_date = delivery_date.date()
            
            if date_finished > delivery_date:
                days_late = (date_finished - delivery_date).days
                
                raise ValidationError(_(
                    "⚠️ ALERTE DÉPASSEMENT DATE DE LIVRAISON ⚠️\n\n"
                    "OF : %s\n"
                    "Date de fin calculée : %s\n"
                    "Date de livraison promise : %s\n"
                    "Retard : %d jours\n\n"
                    "La fabrication se terminera APRÈS la date promise au client !"
                ) % (
                    self.name,
                    date_finished.strftime('%d/%m/%Y'),
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
