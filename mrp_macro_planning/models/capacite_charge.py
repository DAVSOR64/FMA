# -*- coding: utf-8 -*-
from odoo import models, fields, tools
import logging

_logger = logging.getLogger(__name__)


class CapaciteCache(models.Model):
    _name = 'mrp.capacite.cache'
    _description = 'Cache capacité planning par poste/jour'
    _auto = True

    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Poste', index=True, ondelete='cascade')
    workcenter_name = fields.Char(string='Nom poste')
    date = fields.Date(string='Date', index=True)
    capacite_heures = fields.Float(string='Capacité (h)', digits=(10, 2))

    def refresh(self):
        """Recalcule la capacité en tenant compte des calendriers."""
        self.search([]).unlink()

        slots = self.env['planning.slot'].search([('state', '=', 'published')])
        _logger.info('REFRESH CAPACITE : %d slots publiés trouvés', len(slots))

        if not slots:
            return

        vals_list = []

        for slot in slots:
            if not slot.resource_id:
                _logger.info('Slot %s sans resource_id, ignoré', slot.id)
                continue
            if not slot.role_id:
                _logger.info('Slot %s sans role_id, ignoré', slot.id)
                continue

            workcenter = self.env['mrp.workcenter'].search([
                ('name', '=ilike', slot.role_id.name)
            ], limit=1)
            if not workcenter:
                _logger.info('Aucun workcenter pour role "%s"', slot.role_id.name)
                continue

            calendar = slot.resource_id.calendar_id
            if not calendar:
                delta = (slot.end_datetime - slot.start_datetime).total_seconds() / 3600.0
                _logger.info('Slot %s sans calendrier, durée brute: %.2f h', slot.id, delta)
                vals_list.append({
                    'workcenter_id': workcenter.id,
                    'workcenter_name': workcenter.name,
                    'date': slot.start_datetime.date(),
                    'capacite_heures': delta,
                })
                continue

            try:
                intervals = calendar._work_intervals_batch(
                    slot.start_datetime,
                    slot.end_datetime,
                    resources=slot.resource_id,
                )
                resource_intervals = intervals.get(slot.resource_id.id, [])

                heures_par_jour = {}
                for start, stop, _meta in resource_intervals:
                    jour = start.date()
                    duree = (stop - start).total_seconds() / 3600.0
                    heures_par_jour[jour] = heures_par_jour.get(jour, 0) + duree

                _logger.info('Slot %s workcenter=%s : %s',
                    slot.id, workcenter.name, heures_par_jour)

                for jour, heures in heures_par_jour.items():
                    if heures > 0:
                        vals_list.append({
                            'workcenter_id': workcenter.id,
                            'workcenter_name': workcenter.name,
                            'date': jour,
                            'capacite_heures': heures,
                        })

            except Exception as e:
                _logger.error('Erreur slot %s : %s', slot.id, e)
                continue

        aggregated = {}
        for v in vals_list:
            key = (v['workcenter_id'], str(v['date']))
            if key in aggregated:
                aggregated[key]['capacite_heures'] += v['capacite_heures']
            else:
                aggregated[key] = v.copy()

        if aggregated:
            self.create(list(aggregated.values()))

        _logger.info('REFRESH CAPACITE TERMINÉ : %d entrées créées', len(aggregated))


class CapaciteRefreshWizard(models.TransientModel):
    _name = 'mrp.capacite.refresh.wizard'
    _description = 'Wizard recalcul capacité'

    nb_slots = fields.Integer(string='Slots publiés', readonly=True)
    nb_entries = fields.Integer(string='Entrées calculées', readonly=True)
    message = fields.Char(string='Résultat', readonly=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        nb = self.env['planning.slot'].search_count([('state', '=', 'published')])
        res['nb_slots'] = nb
        return res

    def action_refresh(self):
        self.env['mrp.capacite.cache'].refresh()
        nb = self.env['mrp.capacite.cache'].search_count([])
        self.write({
            'nb_entries': nb,
            'message': '%d entrées capacité calculées depuis %d slots' % (nb, self.nb_slots),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class CapaciteCharge(models.Model):
    _name = 'mrp.capacite.charge'
    _auto = False
    _description = 'Capacité vs Charge par poste de travail'
    _order = 'date asc, workcenter_name asc'

    date = fields.Date(string='Date', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste de travail', readonly=True)
    workcenter_name = fields.Char(string='Poste', readonly=True)
    capacite_heures = fields.Float(string='Capacité (h)', digits=(10, 2), readonly=True)
    charge_heures = fields.Float(string='Charge restante (h)', digits=(10, 2), readonly=True)
    nb_operations = fields.Integer(string='Nb opérations', readonly=True)
    taux_charge = fields.Float(string='Taux charge (%)', digits=(10, 1), readonly=True)
    solde_heures = fields.Float(string='Solde (h)', digits=(10, 2), readonly=True)

    def _get_name_expr(self, table, col='name'):
        cr = self.env.cr
        cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s LIMIT 1
        """, (table, col))
        row = cr.fetchone()
        dtype = row[0] if row else 'character varying'
        if dtype == 'jsonb':
            return (f"COALESCE({table}.{col}->>'fr_FR', "
                    f"{table}.{col}->>'en_US', {table}.{col}::text)")
        return f"{table}.{col}::text"

    def action_open_refresh_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Recalculer la capacité',
            'res_model': 'mrp.capacite.refresh.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'mrp_capacite_charge')
        wc_name = self._get_name_expr('mrp_workcenter')

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW mrp_capacite_charge AS (

            WITH charge AS (
                SELECT
                    wo.workcenter_id,
                    {wc_name}                                   AS workcenter_name,
                    DATE(wo.date_start)                         AS date,
                    COUNT(*)                                    AS nb_operations,
                    SUM(
                        CASE
                            WHEN wo.state IN ('pending', 'ready', 'waiting')
                                THEN COALESCE(wo.duration_expected, 0) / 60.0
                            ELSE GREATEST(
                                COALESCE(wo.duration_expected, 0)
                                - COALESCE(wo.duration, 0), 0
                            ) / 60.0
                        END
                    )                                           AS charge_heures
                FROM mrp_workorder wo
                JOIN mrp_workcenter ON mrp_workcenter.id = wo.workcenter_id
                WHERE wo.state NOT IN ('done', 'cancel')
                  AND wo.date_start IS NOT NULL
                GROUP BY
                    wo.workcenter_id,
                    {wc_name},
                    DATE(wo.date_start)
            ),

            capacite AS (
                SELECT
                    workcenter_id,
                    workcenter_name,
                    date,
                    SUM(capacite_heures) AS capacite_heures
                FROM mrp_capacite_cache
                GROUP BY workcenter_id, workcenter_name, date
            ),

            all_keys AS (
                SELECT workcenter_id, workcenter_name, date FROM charge
                UNION
                SELECT workcenter_id, workcenter_name, date FROM capacite
            )

            SELECT
                ROW_NUMBER() OVER (ORDER BY ak.date, ak.workcenter_name) AS id,
                ak.workcenter_id,
                ak.workcenter_name,
                ak.date,
                COALESCE(cap.capacite_heures, 0)       AS capacite_heures,
                COALESCE(ch.charge_heures, 0)          AS charge_heures,
                COALESCE(ch.nb_operations, 0)          AS nb_operations,
                COALESCE(ch.charge_heures, 0)
                    - COALESCE(cap.capacite_heures, 0) AS solde_heures,
                CASE
                    WHEN COALESCE(cap.capacite_heures, 0) > 0
                        THEN ROUND((
                            COALESCE(ch.charge_heures, 0)
                            / cap.capacite_heures * 100.0
                        )::numeric, 1)
                    WHEN COALESCE(ch.charge_heures, 0) > 0 THEN 999
                    ELSE 0
                END AS taux_charge
            FROM all_keys ak
            LEFT JOIN charge   ch  ON ch.workcenter_id = ak.workcenter_id
                                   AND ch.date          = ak.date
            LEFT JOIN capacite cap ON cap.workcenter_id = ak.workcenter_id
                                   AND cap.date         = ak.date
        )
        """)
