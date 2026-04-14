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
    


    def _planning_operation_rank(self, wo):
        """Retourne un rang métier stable pour l'ordre des opérations FMA."""
        self.ensure_one()
        label = " ".join(filter(None, [
            getattr(wo, 'name', '') or '',
            getattr(getattr(wo, 'operation_id', False), 'name', '') or '',
            getattr(getattr(wo, 'workcenter_id', False), 'name', '') or '',
        ])).lower()

        mapping = [
            ('débit', 10), ('debit', 10),
            ('cu', 20), ('banc', 20),
            ('usinage', 30),
            ('montage', 40),
            ('vitrage', 50),
            ('emballage', 60),
        ]
        for token, rank in mapping:
            if token in label:
                return rank
        return 999

    def _ordered_workorders_for_planning(self, include_progress=True):
        """Renvoie les OT éligibles au planning dans l'ordre métier, sans rien écrire."""
        self.ensure_one()
        workorders = self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel'))
        if not include_progress:
            workorders = workorders.filtered(lambda w: w.state != 'progress')
        return workorders.sorted(lambda w: (self._planning_operation_rank(w), (w.operation_id.sequence if w.operation_id else 0), w.id))

    def _resequence_workorders_for_planning(self, workorders):
        """Sécurise le flux de planning sans modifier les séquences standard Odoo."""
        self.ensure_one()
        if not workorders:
            return workorders
        return workorders.sorted(lambda w: (self._planning_operation_rank(w), (w.operation_id.sequence if w.operation_id else 0), w.id))

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


    def _debug_log_wo_db_state(self, wo, label):
        """Trace ORM + SQL pour comprendre pourquoi les dates OT ne restent pas."""
        self.ensure_one()
        field_names = [f for f in ("macro_planned_start", "date_start", "date_finished") if f in wo._fields]
        try:
            wo.flush_recordset(field_names)
        except Exception:
            pass
        try:
            wo.invalidate_recordset(field_names)
        except Exception:
            pass

        _logger.info(
            "TRACE %s | ORM | WO %s (id=%s) | macro=%s | date_start=%s | date_finished=%s",
            label, wo.name, wo.id,
            getattr(wo, "macro_planned_start", False),
            getattr(wo, "date_start", False),
            getattr(wo, "date_finished", False),
        )

        try:
            self.env.cr.execute(
                """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_name = 'mrp_workorder'
                   AND column_name IN ('macro_planned_start', 'macro_planned_finished', 'date_start', 'date_finished')
                ORDER BY column_name
                """
            )
            cols = [r[0] for r in self.env.cr.fetchall()]
            if cols:
                query = "SELECT %s FROM mrp_workorder WHERE id = %%s" % ", ".join(cols)
                self.env.cr.execute(query, (wo.id,))
                row = self.env.cr.fetchone()
                _logger.info("TRACE %s | SQL | WO %s (id=%s) | %s", label, wo.name, wo.id, dict(zip(cols, row or [])))
        except Exception as e:
            _logger.info("TRACE %s | SQL | WO %s (id=%s) | erreur lecture SQL: %s", label, wo.name, wo.id, e)

    def _force_write_wo_dates_sql(self, wo, macro_dt=False, macro_end_dt=False, start_dt=False, end_dt=False, nb_resources=False, write_real_dates=True):
        """Fallback SQL si l'ORM n'a pas persisté les dates OT."""
        sets = []
        params = []

        def _add(col, val):
            self.env.cr.execute(
                """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_name = 'mrp_workorder'
                   AND column_name = %s
                """,
                (col,)
            )
            if self.env.cr.fetchone():
                sets.append(f"{col} = %s")
                params.append(val)

        def _sql_dt(val):
            return fields.Datetime.to_string(val) if val else None

        _add('macro_planned_start', _sql_dt(macro_dt))
        _add('macro_planned_finished', _sql_dt(macro_end_dt))
        if write_real_dates:
            _add('date_start', _sql_dt(start_dt))
            _add('date_finished', _sql_dt(end_dt))
        if nb_resources is not False:
            _add('x_nb_resources', nb_resources)

        if not sets:
            _logger.info("TRACE FORCE SQL | WO %s (id=%s) | aucune colonne trouvée", wo.name, wo.id)
            return

        params.append(wo.id)
        sql = "UPDATE mrp_workorder SET %s WHERE id = %%s" % ", ".join(sets)
        self.env.cr.execute(sql, params)
        _logger.warning(
            "TRACE FORCE SQL | WO %s (id=%s) | SQL fallback exécuté | macro=%s | macro_end=%s | start=%s | end=%s | nb=%s | real=%s",
            wo.name, wo.id, macro_dt, macro_end_dt, start_dt, end_dt, nb_resources, write_real_dates
        )

    def _write_wo_schedule_debug(self, wo, macro_dt, start_dt, end_dt, nb_resources=1, macro_end_dt=False, write_real_dates=True):
        """Écrit les dates OT et pose des traces fortes. Fallback SQL si l'ORM n'écrit rien."""
        self.ensure_one()
        self._debug_log_wo_db_state(wo, 'BEFORE WRITE')

        vals = {}
        if 'macro_planned_start' in wo._fields:
            vals['macro_planned_start'] = macro_dt
        if 'macro_planned_finished' in wo._fields:
            vals['macro_planned_finished'] = macro_end_dt
        if write_real_dates and 'date_start' in wo._fields:
            vals['date_start'] = start_dt
        if write_real_dates and 'date_finished' in wo._fields:
            vals['date_finished'] = end_dt
        if 'x_nb_resources' in wo._fields:
            vals['x_nb_resources'] = nb_resources

        _logger.info("TRACE WRITE PREPARE | WO %s (id=%s) | vals=%s", wo.name, wo.id, vals)

        if vals:
            wo.with_context(
                mail_notrack=True,
                skip_macro_recalc=True,
                skip_shift_chain=True,
                allow_wo_clear=True,
            ).write(vals)

        self._debug_log_wo_db_state(wo, 'AFTER ORM WRITE')

        # fallback dur si l'ORM n'a rien laissé en base
        tracked_fields = [f for f in ('macro_planned_start', 'macro_planned_finished', 'date_start', 'date_finished') if f in wo._fields]
        wo.invalidate_recordset(tracked_fields)
        needs_sql = (
            ('macro_planned_start' in wo._fields and macro_dt and not wo.macro_planned_start)
            or ('macro_planned_finished' in wo._fields and macro_end_dt and not wo.macro_planned_finished)
        )
        if write_real_dates:
            needs_sql = needs_sql or (
                ('date_start' in wo._fields and start_dt and not wo.date_start)
                or ('date_finished' in wo._fields and end_dt and not wo.date_finished)
            )
        if needs_sql:
            self._force_write_wo_dates_sql(wo, macro_dt, macro_end_dt, start_dt, end_dt, nb_resources, write_real_dates=write_real_dates)
            self.env.cr.commit()
            self._debug_log_wo_db_state(wo, 'AFTER SQL FALLBACK')

    def _restore_wo_schedule_after_mo_update(self, wo_payloads):
        """Réapplique les dates OT après écriture sur l'OF, car Odoo peut les vider."""
        self.ensure_one()
        for payload in wo_payloads:
            wo = payload.get('wo')
            if not wo or not wo.exists():
                continue
            self._write_wo_schedule_debug(
                wo,
                payload.get('macro_dt'),
                payload.get('start_dt'),
                payload.get('end_dt'),
                payload.get('nb_resources', 1),
                macro_end_dt=payload.get('macro_end_dt'),
                write_real_dates=payload.get('write_real_dates', True),
            )
        self.env.cr.flush()

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
        raw_delivery = getattr(sale_order, "so_date_de_livraison_prevu", False) \
            or getattr(sale_order, "x_studio_date_de_livraison_prevu", False) \
            or sale_order.commitment_date

        delivery_dt = fields.Datetime.to_datetime(raw_delivery)
        if not delivery_dt:
            _logger.info("SO %s : pas de date prévue de livraison -> pas de macro planning", sale_order.name)
            return False


        self.message_post(body="🧪 DEBUG : macro planning (SO confirm) exécuté")

        workorders = self._resequence_workorders_for_planning(self._ordered_workorders_for_planning(include_progress=True))
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
            duration_hours, nb_resources = self._get_effective_duration_hours(wo)
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            # Bloc de required_days se terminant à current_end_day
            last_day = self._previous_or_same_working_day(current_end_day, wc)
            first_day = last_day
            for _ in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)

            # macro_planned_start = début du bloc (matin)
            macro_dt = self._morning_dt(first_day, wc)
            end_dt = self._evening_dt(last_day, wc)

            self._write_wo_schedule_debug(wo, macro_dt, False, False, nb_resources, macro_end_dt=end_dt, write_real_dates=False)

            _logger.info(
                "WO %s (%s): %s -> %s | brut=%.0f min | eff=%.2fh => %d j | %d ressource(s) | macro=%s",
                wo.name, wc.display_name, first_day, last_day,
                wo.duration_expected or 0, duration_hours, required_days, nb_resources, macro_dt
            )

            # Décalage "veille ouvrée" entre opérations
            current_end_day = self._previous_working_day(first_day, wc)

        wo_payloads = []
        for wo in workorders:
            self.env.cr.execute(
                "SELECT macro_planned_start, macro_planned_finished, date_start, date_finished FROM mrp_workorder WHERE id = %s",
                (wo.id,)
            )
            row = self.env.cr.fetchone()
            wo_payloads.append({
                'wo': wo,
                'macro_dt': row[0] if row else False,
                'macro_end_dt': row[1] if row else False,
                'start_dt': False,
                'end_dt': False,
                'write_real_dates': False,
                'nb_resources': getattr(wo, 'x_nb_resources', 1) or 1,
            })
            _logger.info("TRACE SALE FINAL SQL | WO %s (id=%s) | macro=%s | date_start=%s | date_finished=%s",
                wo.name, wo.id, row[0] if row else 'NULL', row[1] if row else 'NULL', row[2] if row else 'NULL')

        # ✅ Recaler l'OF depuis les macros WO
        self._update_mo_dates_from_macro(forced_end_dt=end_fab_dt)

        # ✅ Réappliquer les OT après update OF
        self._restore_wo_schedule_after_mo_update(wo_payloads)

        # ✅ Recaler les pickings composants depuis le début fab (MO.date_start)
        self._update_components_picking_dates()

        return True

    # ============================================================
    # ENTRY POINT FROM REPLANIFIER (date_fin custom -> backward)
    # ============================================================
    def compute_macro_schedule_from_date_fin(self):
        """
        Appelé par le bouton Replanifier (via action_apply_replan_preview).
        - Source : x_studio_date_de_fin (saisi par l'utilisateur)
        - Bloque si x_studio_date_de_fin > so_date_de_livraison_prevu
        - Calcule backward depuis x_studio_date_de_fin
        - Écrit macro_planned_start + macro_planned_finished sur chaque WO
        - Met à jour dates OF + transfert composants
        """
        self.ensure_one()
        from odoo.exceptions import UserError, ValidationError

        # 1) Récupérer x_studio_date_de_fin
        x_end = (
            getattr(self, 'x_studio_date_de_fin', False)
            or getattr(self, 'x_studio_date_fin', False)
        )
        if not x_end:
            raise UserError(_("La date de fin de fabrication (x_studio_date_de_fin) n'est pas renseignée sur l'OF."))

        # Convertir en date si nécessaire
        from datetime import date as date_type
        if not isinstance(x_end, date_type):
            x_end = fields.Date.to_date(x_end)

        workorders = self._resequence_workorders_for_planning(self._ordered_workorders_for_planning(include_progress=True))
        if not workorders:
            raise UserError(_("Aucune opération active à replanifier sur cet OF."))

        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        # 2) Récupérer la date de livraison client
        delivery_dt, sale_order = self._get_macro_target_date()

        # 3) Blocage si date de fin fab > date de livraison
        if delivery_dt:
            delivery_date = delivery_dt.date() if hasattr(delivery_dt, 'date') else delivery_dt
            if x_end > delivery_date:
                days_late = (x_end - delivery_date).days
                raise ValidationError(_(
                    "⚠️ BLOCAGE : La date de fin de fabrication dépasse la date de livraison client !\n\n"
                    "Date de fin fab :    %s\n"
                    "Date de livraison :  %s\n"
                    "Retard :             %d jours\n\n"
                    "Modifiez la date de fin ou négociez la date de livraison avant de replanifier."
                ) % (
                    x_end.strftime('%d/%m/%Y'),
                    delivery_date.strftime('%d/%m/%Y'),
                    days_late,
                ))

        # 4) Convertir x_end en datetime fin de journée
        last_wc_sorted = workorders[-1].workcenter_id
        end_fab_dt = self._evening_dt(x_end, last_wc_sorted) if last_wc_sorted \
            else datetime.combine(x_end, time(17, 0))

        _logger.info("MO %s : REPLANIFIER depuis x_studio_date_de_fin=%s → end_fab_dt=%s",
                     self.name, x_end, end_fab_dt)

        # 5) Backward : dernière opération → première
        end_fab_day = x_end
        last_wc = workorders[-1].workcenter_id
        current_end_day = self._previous_or_same_working_day(end_fab_day, last_wc)

        for wo in workorders.sorted(
            lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id), reverse=True
        ):
            wc = wo.workcenter_id
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8

            duration_hours, nb_resources = self._get_effective_duration_hours(wo)
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

            last_day = self._previous_or_same_working_day(current_end_day, wc)
            first_day = last_day
            for _ in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)

            macro_dt = self._morning_dt(first_day, wc)
            end_dt = self._evening_dt(last_day, wc)

            self._write_wo_schedule_debug(wo, macro_dt, False, False, nb_resources, macro_end_dt=end_dt, write_real_dates=False)

            _logger.info(
                "WO %s (%s): %s -> %s | eff=%.2fh | %d j | macro=%s",
                wo.name, wc.display_name, first_day, last_day,
                duration_hours, required_days, macro_dt
            )

            current_end_day = self._previous_working_day(first_day, wc)

        # Vérification SQL finale AVANT _update_mo_dates_from_macro + backup
        wo_payloads = []
        for wo in workorders:
            self.env.cr.execute(
                "SELECT macro_planned_start, macro_planned_finished, date_start, date_finished FROM mrp_workorder WHERE id = %s",
                (wo.id,)
            )
            row = self.env.cr.fetchone()
            wo_payloads.append({
                'wo': wo,
                'macro_dt': row[0] if row else False,
                'macro_end_dt': row[1] if row else False,
                'start_dt': False,
                'end_dt': False,
                'write_real_dates': False,
                'nb_resources': getattr(wo, 'x_nb_resources', 1) or 1,
            })
            _logger.info("TRACE FINAL SQL | WO %s (id=%s) | macro=%s | date_start=%s | date_finished=%s",
                wo.name, wo.id, row[0] if row else 'NULL', row[1] if row else 'NULL', row[2] if row else 'NULL')

        # 6) Recaler les dates OF + transfert composants
        self._update_mo_dates_from_macro(forced_end_dt=end_fab_dt)

        # 7) Restaurer immédiatement les OT écrasés par l'update OF
        self._restore_wo_schedule_after_mo_update(wo_payloads)

        self._update_components_picking_dates()

        # Vérification SQL APRÈS restauration
        for wo in workorders:
            self.env.cr.execute(
                "SELECT macro_planned_start, macro_planned_finished, date_start, date_finished FROM mrp_workorder WHERE id = %s",
                (wo.id,)
            )
            row = self.env.cr.fetchone()
            _logger.info("TRACE POST-RESTORE SQL | WO %s (id=%s) | macro=%s | date_start=%s | date_finished=%s",
                wo.name, wo.id, row[0] if row else 'NULL', row[1] if row else 'NULL', row[2] if row else 'NULL')

        _logger.info("MO %s : REPLANIFIER terminé", self.name)
        return True


    def button_plan(self):
        _logger.warning("********** BUTTON_PLAN FROM MACRO **********")

        for production in self:
            for wo in production.workorder_ids.sorted(
                key=lambda w: (w.macro_planned_start or w.date_start or production.date_planned_start or fields.Datetime.now())
            ):
                macro_start = wo.macro_planned_start
                if not macro_start:
                    continue

                # Forcer l'heure à 07:30
                start_dt = macro_start.replace(hour=7, minute=30, second=0, microsecond=0)

                duration_hours, nb_resources = production._get_effective_duration_hours(wo)
                if duration_hours <= 0:
                    duration_hours = 0.01

                end_dt = start_dt + timedelta(hours=duration_hours)

                vals = {
                    'date_start': start_dt,
                    'date_finished': end_dt,
                }

                if 'date_planned_start' in wo._fields:
                    vals['date_planned_start'] = start_dt
                if 'date_planned_finished' in wo._fields:
                    vals['date_planned_finished'] = end_dt

                wo.write(vals)

        return True

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
                    "macro_planned_finished": False,
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

        workorders = self._resequence_workorders_for_planning(self._ordered_workorders_for_planning(include_progress=True))
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
        """Pose les dates réelles des OT lors du clic sur Programmer.

        On écrit toujours les champs réels visibles dans l'UI (Lancer / Fin),
        et on complète aussi les champs planifiés quand ils existent.
        """
        vals = {}

        # Champs réels visibles dans les OT / gantt atelier
        if "date_start" in wo._fields:
            vals["date_start"] = start_dt
        if "date_finished" in wo._fields:
            vals["date_finished"] = end_dt

        # Champs planifiés complémentaires selon la version Odoo
        if "date_planned_start" in wo._fields:
            vals["date_planned_start"] = start_dt
        if "date_planned_finished" in wo._fields:
            vals["date_planned_finished"] = end_dt

        if vals:
            wo.with_context(
                mail_notrack=True,
                skip_shift_chain=True,
                skip_macro_recalc=True,
            ).write(vals)

            # Fallback SQL si l'ORM ne persiste pas bien les dates réelles
            wo.invalidate_recordset([f for f in ("date_start", "date_finished", "date_planned_start", "date_planned_finished") if f in wo._fields])
            missing_real = (
                ("date_start" in wo._fields and not wo.date_start) or
                ("date_finished" in wo._fields and not wo.date_finished)
            )
            if missing_real:
                sets = []
                params = []

                def _add(col, val):
                    self.env.cr.execute(
                        """
                        SELECT 1
                          FROM information_schema.columns
                         WHERE table_name = 'mrp_workorder'
                           AND column_name = %s
                        """,
                        (col,)
                    )
                    if self.env.cr.fetchone():
                        sets.append(f"{col} = %s")
                        params.append(fields.Datetime.to_string(val) if val else None)

                _add('date_start', start_dt)
                _add('date_finished', end_dt)
                _add('date_planned_start', start_dt)
                _add('date_planned_finished', end_dt)
                if sets:
                    params.append(wo.id)
                    sql = "UPDATE mrp_workorder SET %s WHERE id = %%s" % ", ".join(sets)
                    self.env.cr.execute(sql, params)
                    _logger.warning(
                        "BUTTON_PLAN fallback SQL | WO %s (id=%s) | start=%s | end=%s",
                        wo.name, wo.id, start_dt, end_dt
                    )


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
        # Important: éviter de réécrire trop de champs OF, car Odoo 17 peut vider les dates OT.
        if "date_finished" in self._fields:
            vals["date_finished"] = end_dt
        if "date_planned_finished" in self._fields:
            vals["date_planned_finished"] = end_dt
        if "date_deadline" in self._fields:
            vals["date_deadline"] = end_dt
        # On conserve date_start uniquement si vraiment présent, mais après les OT seront restaurés.
        if "date_start" in self._fields:
            vals["date_start"] = start_dt
        if "date_planned_start" in self._fields:
            vals["date_planned_start"] = start_dt
    
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
        """Bouton « Replanifier » sur le formulaire OF.

        Recalcule les dates macro de tous les workorders en rétroplanning
        et met à jour le cache charge. Ouvre le wizard de prévisualisation
        si le module mrp_replan_workorder_popup est installé, sinon
        applique directement.
        """
        self.ensure_one()
        # Déléguer au popup si disponible
        if hasattr(self, 'action_open_replan_preview'):
            return self.action_open_replan_preview()

        # Fallback : application directe sans prévisualisation
        workorders = self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel'))
        if not workorders:
            raise UserError(_("Aucune opération à replanifier sur cet OF."))

        fixed_end_dt = (
            getattr(self, 'macro_forced_end', False)
            or self.date_deadline
            or getattr(self, 'date_finished', False)
        )
        if not fixed_end_dt:
            raise UserError(_("Aucune date de fin définie sur l'OF."))

        ctx = self.with_context(skip_macro_recalc=True)
        ctx._recalculate_macro_backward(workorders, end_dt=fixed_end_dt)
        ctx.apply_macro_to_workorders_dates()
        ctx._update_mo_dates_from_macro(forced_end_dt=fixed_end_dt)
        ctx._update_components_picking_dates()
        self._refresh_charge_cache_for_production()
        return True

    @api.model
    def cron_replan_all_productions(self):
        """
        Cron 13h / 18h aligné sur le moteur qui fonctionne déjà.
        - OF non lancés : toutes les OT actives
        - OF lancés : uniquement OT non démarrées
        - resequence FMA avant calcul
        """
        import traceback
        from datetime import datetime as dt_now

        _logger.info("=" * 60)
        _logger.info("CRON REPLAN START : %s", dt_now.now().strftime('%d/%m/%Y %H:%M'))
        _logger.info("=" * 60)

        productions = self.search([('state', 'not in', ('done', 'cancel'))])
        stats = {'traites': 0, 'ignores': 0, 'erreurs': 0}

        for mo in productions:
            try:
                x_end = getattr(mo, 'x_studio_date_de_fin', False) or getattr(mo, 'x_studio_date_fin', False)
                if not x_end:
                    stats['ignores'] += 1
                    continue

                delivery_dt, _sale_order = mo._get_macro_target_date()
                if delivery_dt and x_end > delivery_dt.date():
                    _logger.warning("CRON | %s ignoré (date fin > livraison)", mo.name)
                    stats['ignores'] += 1
                    continue

                include_progress = not any(w.state == 'progress' for w in mo.workorder_ids)
                eligible_wos = mo._resequence_workorders_for_planning(
                    mo._ordered_workorders_for_planning(include_progress=include_progress)
                )
                if not eligible_wos:
                    stats['ignores'] += 1
                    continue

                last_wc = eligible_wos[-1].workcenter_id
                end_fab_dt = mo._evening_dt(x_end, last_wc) if last_wc else datetime.combine(x_end, time(17, 0))
                current_end_day = mo._previous_or_same_working_day(x_end, last_wc)
                wo_payloads = []

                for wo in eligible_wos.sorted(lambda w: ((w.operation_id.sequence if w.operation_id else 0), w.id), reverse=True):
                    wc = wo.workcenter_id
                    cal = wc.resource_calendar_id or mo.env.company.resource_calendar_id
                    hours_per_day = cal.hours_per_day or 7.8
                    duration_hours, nb_resources = mo._get_effective_duration_hours(wo)
                    required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))

                    last_day = mo._previous_or_same_working_day(current_end_day, wc)
                    first_day = last_day
                    for _ in range(required_days - 1):
                        first_day = mo._previous_working_day(first_day, wc)

                    macro_dt = mo._morning_dt(first_day, wc)
                    end_dt = mo._evening_dt(last_day, wc)
                    mo._write_wo_schedule_debug(wo, macro_dt, macro_dt, end_dt, nb_resources)
                    wo_payloads.append({'wo': wo, 'macro_dt': macro_dt, 'start_dt': macro_dt, 'end_dt': end_dt, 'nb_resources': nb_resources})
                    current_end_day = mo._previous_working_day(first_day, wc)

                mo._update_mo_dates_from_macro(forced_end_dt=end_fab_dt)
                mo._restore_wo_schedule_after_mo_update(wo_payloads)
                mo._update_components_picking_dates()
                mo._refresh_charge_cache_for_production()
                stats['traites'] += 1
                _logger.info("CRON | %s OK (%d OT)", mo.name, len(eligible_wos))
            except Exception as e:
                stats['erreurs'] += 1
                _logger.error("CRON | %s ERREUR %s\n%s", mo.name, str(e), traceback.format_exc())

        try:
            if 'mrp.workorder.charge.cache' in self.env:
                self.env['mrp.workorder.charge.cache'].refresh()
            if 'mrp.capacite.cache' in self.env:
                self.env['mrp.capacite.cache'].refresh()
            if 'mrp.capacity.week' in self.env and hasattr(self.env['mrp.capacity.week'], 'cron_recompute_absences'):
                self.env['mrp.capacity.week'].cron_recompute_absences()
        except Exception as e:
            _logger.error("CRON refresh erreur : %s", e)

        _logger.info("CRON REPLAN END | %s traités | %s ignorés | %s erreurs", stats['traites'], stats['ignores'], stats['erreurs'])
        _logger.info("=" * 60)
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
        workorders = self._resequence_workorders_for_planning(self._ordered_workorders_for_planning(include_progress=True))
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
        from odoo.exceptions import UserError, ValidationError
        self.ensure_one()

        # Date de fin fab custom
        x_end = (
            getattr(self, 'x_studio_date_de_fin', False)
            or getattr(self, 'x_studio_date_fin', False)
        )
        if not x_end:
            raise UserError(_("La date de fin de fabrication n'est pas renseignée sur l'OF."))

        from datetime import date as date_type
        if not isinstance(x_end, date_type):
            x_end = fields.Date.to_date(x_end)

        workorders = self._resequence_workorders_for_planning(self._ordered_workorders_for_planning(include_progress=True))
        if not workorders:
            raise UserError(_("Aucune opération active à replanifier."))

        workorders = workorders.sorted(lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        # Date de livraison client
        delivery_dt, sale_order = self._get_macro_target_date()

        # Blocage immédiat si retard
        if delivery_dt:
            delivery_date = delivery_dt.date() if hasattr(delivery_dt, 'date') else delivery_dt
            if x_end > delivery_date:
                days_late = (x_end - delivery_date).days
                raise ValidationError(_(
                    "⚠️ BLOCAGE : La date de fin de fabrication dépasse la date de livraison client !\n\n"
                    "Date de fin fab :    %s\n"
                    "Date de livraison :  %s\n"
                    "Retard :             %d jours\n\n"
                    "Modifiez la date de fin ou négociez la date de livraison avant de replanifier."
                ) % (
                    x_end.strftime('%d/%m/%Y'),
                    delivery_date.strftime('%d/%m/%Y'),
                    days_late,
                ))

        def _fmt(dt):
            if not dt:
                return "-"
            try:
                if hasattr(dt, 'strftime'):
                    return dt.strftime('%d/%m/%Y')
                d = str(dt)[:10].split('-')
                return f"{d[2]}/{d[1]}/{d[0]}"
            except Exception:
                return str(dt)[:10]

        # Calcul à sec des dates pour le popup (sans écrire en base)
        end_fab_day = x_end
        last_wc = workorders[-1].workcenter_id
        current_end_day = self._previous_or_same_working_day(end_fab_day, last_wc)
        first_start_day = None

        for wo in workorders.sorted(
            lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id), reverse=True
        ):
            wc = wo.workcenter_id
            if not wc:
                continue
            cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
            hours_per_day = cal.hours_per_day or 7.8
            duration_hours, ignored_nb = self._get_effective_duration_hours(wo)
            required_days = max(1, int(math.ceil(duration_hours / hours_per_day)))
            last_day = self._previous_or_same_working_day(current_end_day, wc)
            first_day = last_day
            for day_idx in range(required_days - 1):
                first_day = self._previous_working_day(first_day, wc)
            first_start_day = first_day
            current_end_day = self._previous_working_day(first_day, wc)

        # Date début OF
        first_wc = workorders[0].workcenter_id
        new_start = self._morning_dt(first_start_day, first_wc) if first_start_day else None

        # Date transfert = 4 jours ouvrés avant début fab
        transfer_day = first_start_day
        if transfer_day:
            for transfer_idx in range(4):
                transfer_day = self._previous_working_day(transfer_day, first_wc)

        # POs liés
        purchase_orders = self.env["purchase.order"]
        if self.procurement_group_id:
            po_lines = self.env["purchase.order.line"].search([
                ("move_dest_ids.group_id", "=", self.procurement_group_id.id),
            ])
            purchase_orders = po_lines.mapped("order_id")

        po_data = [{
            "name": po.name or "",
            "partner": po.partner_id.display_name or "",
            "date_planned": str(po.date_planned)[:10] if po.date_planned else "",
        } for po in purchase_orders]

        return {
            "production_name": self.display_name or self.name or "",
            "date_fin_fab": _fmt(x_end),
            "date_start": _fmt(new_start),
            "transfer_date": _fmt(datetime.combine(transfer_day, time(7, 30)) if transfer_day else None),
            "date_livraison": _fmt(delivery_dt) if delivery_dt else "-",
            "retard": False,  # déjà bloqué au-dessus si retard
            "purchase_orders": po_data,
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
        """Appelé au clic OK du popup de prévisualisation."""
        self.ensure_one()
        self.compute_macro_schedule_from_date_fin()
        return True

    def _apply_replan_real(self, payload=None):
        return self.action_apply_replan_preview(payload)
