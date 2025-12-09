import pytz
from datetime import datetime, time
from odoo import api, models, fields


class MrpWorkOrder(models.Model):
    _inherit = "mrp.workorder"

    date_macro = fields.Datetime("Macro Date")


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # -----------------------------
    # Confirmation ordre de fabrication
    # -----------------------------
    def action_confirm(self):
        res = super().action_confirm()
        # Recalcul APRES la création des mouvements -> évite le bug
        self._compute_date_macro()
        return res

    # -----------------------------
    # Write sécurisé
    # -----------------------------
    def write(self, vals):
        # Exécution normale
        res = super().write(vals)

        # Éviter les boucles internes
        if self.env.context.get("no_recompute"):
            return res

        # Ignorer si Odoo modifie des moves (évite "Opération invalide")
        forbidden_fields = [
            "move_raw_ids",
            "move_finished_ids",
            "move_byproduct_ids",
            "move_dest_ids",
            "move_line_ids",
        ]

        if any(key in vals for key in forbidden_fields):
            return res

        # Recalcul seulement quand on modifie des données pertinentes
        compute_fields = [
            "workorder_ids",
            "date_start",
            "date_finished",
            "routing_id",
            "bom_id",
        ]

        if any(key in vals for key in compute_fields):
            self._compute_date_macro()

        return res

    # -----------------------------
    # Fonction de calcul Macro Date
    # -----------------------------
    def _compute_date_macro(self):
        for production in self:
            # *** AJOUT: Vérifier l'état de l'OF ***
            # Ne pas recalculer si l'OF est terminé ou annulé
            if production.state in ("done", "cancel"):
                continue

            # -----------------------------
            # 1) Récupération date livraison
            # -----------------------------
            date_delivery = (
                production.procurement_group_id.mrp_production_ids.move_dest_ids.group_id.sale_id.commitment_date
                or production.date_finished
            )

            manufacturing_lead = production.company_id.manufacturing_lead
            calendar = production.company_id.resource_calendar_id or self.env.ref(
                "resource.resource_calendar_std"
            )

            # -----------------------------
            # 2) Calcul deadline
            # -----------------------------
            deadline_production = calendar.plan_days(-manufacturing_lead, date_delivery)
            last_date = calendar.plan_days(-1, deadline_production)

            # -----------------------------
            # 3) Calcul par ordre de travail
            # -----------------------------
            for work in production.workorder_ids.sorted("id", reverse=True):
                workcenter_calendar = (
                    work.workcenter_id.resource_calendar_id or calendar
                )
                work.date_macro = last_date

                # Récupération de la première plage horaire
                last_date2 = workcenter_calendar._attendance_intervals_batch(
                    datetime.combine(last_date, time.min).replace(tzinfo=pytz.UTC),
                    datetime.combine(last_date, time.max).replace(tzinfo=pytz.UTC),
                    resources=work.workcenter_id.resource_id,
                )

                if last_date2 and work.workcenter_id.resource_id.id in last_date2:
                    first_interval = last_date2[
                        work.workcenter_id.resource_id.id
                    ]._items
                    if first_interval:
                        first_date = first_interval[0][0]
                        last_date = last_date.replace(
                            hour=first_date.hour, minute=0, second=0, microsecond=0
                        )

                # Calcul backward
                last_date = workcenter_calendar.plan_hours(
                    -work.duration_expected / 60, last_date
                )
                last_date = workcenter_calendar.plan_days(-1, last_date)

            # -----------------------------
            # 4) Mise à jour sécurisée OF
            # -----------------------------
            if production.workorder_ids:
                all_dates = [
                    w.date_macro for w in production.workorder_ids if w.date_macro
                ]
                if all_dates:
                    # *** MODIFICATION: Vérifier à nouveau l'état avant la mise à jour ***
                    if production.state not in ("done", "cancel"):
                        production.sudo().with_context(no_recompute=True).write(
                            {
                                "date_start": min(all_dates),
                                "date_finished": max(all_dates),
                            }
                        )
