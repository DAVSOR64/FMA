# -*- coding: utf-8 -*-
import logging
from datetime import date, datetime, time, timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class MrpDailySnapshot(models.Model):
    """
    Snapshot quotidien du retard/avance par OT et par poste.
    Calculé chaque soir à 23H30 par le cron.

    Logique de capture :
      1. OTs avec macro_planned_start = aujourd'hui (prévus ce jour)
      2. OTs en progress avec macro_planned_start < aujourd'hui (glissement)
      3. OTs non démarrés avec macro_planned_start < aujourd'hui (pas lancés)

    Calcul delta_hours (en heures) :
      - OT done    : duration_expected_h - duration_real_h  (+ = avance, - = retard)
      - OT progress: -(duration_expected_h - duration_real_h) si pas fini = retard
      - OT non démarré : -duration_expected_h (retard total)

    Le retard cumulé par poste = somme des delta négatifs depuis le début.
    """
    _name = 'mrp.daily.snapshot'
    _description = 'Snapshot quotidien retard atelier'
    _order = 'snapshot_date desc, workcenter_id, production_id'
    _rec_name = 'display_name'

    # ── Clés ────────────────────────────────────────────────────────────────
    snapshot_date = fields.Date(
        string='Date snapshot',
        required=True,
        index=True,
        help="Date du snapshot (fin de journée)",
    )
    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Poste de travail',
        required=True,
        index=True,
    )
    workorder_id = fields.Many2one(
        'mrp.workorder',
        string='Ordre de travail',
        required=True,
        index=True,
        ondelete='cascade',
    )
    production_id = fields.Many2one(
        'mrp.production',
        string='Ordre de fabrication',
        related='workorder_id.production_id',
        store=True,
    )

    # ── Données OT au moment du snapshot ────────────────────────────────────
    wo_name = fields.Char(string='Opération', help="Nom de l'OT au moment du snapshot")
    mo_name = fields.Char(string='OF', help="Référence OF")
    state_at_eod = fields.Selection([
        ('pending',  'En attente'),
        ('waiting',  'En attente composants'),
        ('ready',    'Prêt'),
        ('progress', 'En cours'),
        ('done',     'Terminé'),
        ('cancel',   'Annulé'),
    ], string='État en fin de journée')

    macro_planned_start = fields.Date(
        string='Date macro prévue',
        help="Date macro_planned_start de l'OT",
    )

    # ── Durées (en heures) ───────────────────────────────────────────────────
    duration_expected_h = fields.Float(
        string='Durée prévue (h)',
        digits=(10, 2),
        help="duration_expected converti en heures",
    )
    duration_real_h = fields.Float(
        string='Durée réelle (h)',
        digits=(10, 2),
        help="duration (temps réel saisi) converti en heures",
    )

    # ── KPIs ─────────────────────────────────────────────────────────────────
    delta_hours = fields.Float(
        string='Δ Heures',
        digits=(10, 2),
        help="Positif = avance, Négatif = retard (en heures)",
    )
    is_late = fields.Boolean(
        string='En retard',
        help="True si delta_hours < 0",
    )
    is_done = fields.Boolean(
        string='Terminé',
        help="True si state=done au moment du snapshot",
    )
    capture_reason = fields.Selection([
        ('planned_today',  'Prévu aujourd\'hui'),
        ('in_progress',    'En cours (glissement)'),
        ('not_started',    'Non démarré (glissement)'),
    ], string='Raison de capture')

    # ── Cumulatif par poste ──────────────────────────────────────────────────
    cumul_retard_wc = fields.Float(
        string='Retard cumulé poste (h)',
        digits=(10, 2),
        help="Somme cumulée des retards sur ce poste jusqu'à cette date",
    )

    # ── Affichage ────────────────────────────────────────────────────────────
    display_name = fields.Char(
        string='Libellé',
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('snapshot_date', 'workcenter_id', 'wo_name')
    def _compute_display_name(self):
        for rec in self:
            date_str = rec.snapshot_date.strftime('%d/%m/%Y') if rec.snapshot_date else '-'
            wc = rec.workcenter_id.name or '-'
            wo = rec.wo_name or '-'
            rec.display_name = f"{date_str} | {wc} | {wo}"

    # ── Contrainte d'unicité ─────────────────────────────────────────────────
    _sql_constraints = [
        ('unique_snapshot_wo_date',
         'UNIQUE(snapshot_date, workorder_id)',
         'Un seul snapshot par OT et par journée.'),
    ]

    # ========================================================================
    # MÉTHODE PRINCIPALE : calcul du snapshot quotidien
    # ========================================================================

    @api.model
    def cron_compute_daily_snapshot(self):
        """
        Cron 23H30 : calcule et stocke le snapshot du jour pour tous les OTs
        éligibles. Idempotent : supprime et recrée le snapshot du jour si déjà
        existant (permettant un recalcul manuel en cours de journée).
        """
        import traceback
        today = date.today()

        _logger.info("=" * 60)
        _logger.info("KPI SNAPSHOT START : %s", today.strftime('%d/%m/%Y'))
        _logger.info("=" * 60)

        # Supprimer les éventuels snapshots du jour (idempotent)
        existing = self.search([('snapshot_date', '=', today)])
        if existing:
            _logger.info("KPI SNAPSHOT : suppression de %d snapshots existants du jour", len(existing))
            existing.unlink()

        # ── Récupérer les OTs éligibles ──────────────────────────────────────
        eligible_wos = self._get_eligible_workorders(today)
        _logger.info("KPI SNAPSHOT : %d OTs éligibles trouvés", len(eligible_wos))

        stats = {'created': 0, 'errors': 0}
        snapshots_to_create = []

        for wo in eligible_wos:
            try:
                snap_vals = self._compute_snapshot_vals(wo, today)
                if snap_vals:
                    snapshots_to_create.append(snap_vals)
            except Exception as e:
                _logger.error("KPI SNAPSHOT | OT %s : ERREUR %s\n%s",
                              wo.name, str(e), traceback.format_exc())
                stats['errors'] += 1

        # Créer tous les snapshots en une fois
        if snapshots_to_create:
            created = self.create(snapshots_to_create)
            stats['created'] = len(created)

        # ── Calculer le retard cumulé par poste ──────────────────────────────
        self._compute_cumul_retard(today)

        _logger.info("=" * 60)
        _logger.info("KPI SNAPSHOT END : %d créés | %d erreurs",
                     stats['created'], stats['errors'])
        _logger.info("=" * 60)

    @api.model
    def _get_eligible_workorders(self, today):
        """
        Retourne les OTs à capturer :
          1. macro_planned_start = today (prévus ce jour, quel que soit l'état)
          2. state=progress + macro_planned_start < today (en glissement)
          3. state not in (done,cancel,progress) + macro_planned_start < today (pas démarrés)
        """
        MrpWO = self.env['mrp.workorder']

        # Critère 1 : prévus aujourd'hui
        planned_today = MrpWO.search([
            ('macro_planned_start', '>=', datetime.combine(today, time.min)),
            ('macro_planned_start', '<=', datetime.combine(today, time.max)),
            ('state', 'not in', ['cancel']),
        ])

        # Critère 2 : en cours en glissement
        in_progress_late = MrpWO.search([
            ('macro_planned_start', '<', datetime.combine(today, time.min)),
            ('state', '=', 'progress'),
        ])

        # Critère 3 : non démarrés en glissement
        not_started_late = MrpWO.search([
            ('macro_planned_start', '<', datetime.combine(today, time.min)),
            ('state', 'not in', ['done', 'cancel', 'progress']),
        ])

        all_wos = planned_today | in_progress_late | not_started_late
        _logger.info(
            "KPI SNAPSHOT : prévus aujourd'hui=%d | en glissement progress=%d | non démarrés=%d | total=%d",
            len(planned_today), len(in_progress_late), len(not_started_late), len(all_wos)
        )
        return all_wos

    @api.model
    def _compute_snapshot_vals(self, wo, today):
        """Calcule les valeurs du snapshot pour un OT donné."""
        # Durées en heures (duration_expected et duration en minutes dans Odoo)
        duration_expected_h = (wo.duration_expected or 0.0) / 60.0
        duration_real_h = (wo.duration or 0.0) / 60.0

        # Déterminer la raison de capture
        macro_date = None
        if wo.macro_planned_start:
            macro_date = wo.macro_planned_start.date() if hasattr(wo.macro_planned_start, 'date') else wo.macro_planned_start

        if macro_date == today:
            reason = 'planned_today'
        elif wo.state == 'progress':
            reason = 'in_progress'
        else:
            reason = 'not_started'

        # Calcul du delta
        # OT done : delta = prévu - réel (+ = avance, - = retard si dépassement)
        # OT progress non fini : delta = -(prévu - réel) = retard résiduel négatif
        # OT non démarré : delta = -prévu (retard total)
        if wo.state == 'done':
            delta = duration_expected_h - duration_real_h
        elif wo.state == 'progress':
            # Retard = ce qu'il reste à faire = prévu - réel (négatif = retard)
            remaining = duration_expected_h - duration_real_h
            delta = -remaining  # négatif car non terminé
        else:
            # Non démarré = retard de la totalité des heures prévues
            delta = -duration_expected_h

        is_late = delta < 0
        is_done = wo.state == 'done'

        _logger.info(
            "KPI | OT %s | poste=%s | état=%s | raison=%s | prévu=%.2fh | réel=%.2fh | delta=%.2fh",
            wo.name,
            wo.workcenter_id.name,
            wo.state,
            reason,
            duration_expected_h,
            duration_real_h,
            delta,
        )

        return {
            'snapshot_date': today,
            'workcenter_id': wo.workcenter_id.id,
            'workorder_id': wo.id,
            'wo_name': wo.name,
            'mo_name': wo.production_id.name if wo.production_id else '',
            'state_at_eod': wo.state,
            'macro_planned_start': macro_date,
            'duration_expected_h': duration_expected_h,
            'duration_real_h': duration_real_h,
            'delta_hours': delta,
            'is_late': is_late,
            'is_done': is_done,
            'capture_reason': reason,
            'cumul_retard_wc': 0.0,  # calculé après en batch
        }

    @api.model
    def _compute_cumul_retard(self, today):
        """
        Calcule le retard cumulé par poste de travail jusqu'à aujourd'hui.
        Pour chaque poste : somme de tous les delta_hours négatifs depuis le début.
        """
        _logger.info("KPI SNAPSHOT : calcul retard cumulé par poste")

        # Récupérer tous les postes qui ont des snapshots aujourd'hui
        today_snaps = self.search([('snapshot_date', '=', today)])
        wc_ids = today_snaps.mapped('workcenter_id').ids

        for wc_id in wc_ids:
            # Somme cumulée de tous les deltas négatifs sur ce poste toutes dates confondues
            self.env.cr.execute("""
                SELECT COALESCE(SUM(delta_hours), 0)
                FROM mrp_daily_snapshot
                WHERE workcenter_id = %s
                  AND snapshot_date <= %s
                  AND delta_hours < 0
            """, (wc_id, today))
            row = self.env.cr.fetchone()
            cumul = row[0] if row else 0.0

            # Mettre à jour tous les snapshots du jour pour ce poste
            today_snaps.filtered(
                lambda s: s.workcenter_id.id == wc_id
            ).write({'cumul_retard_wc': cumul})

            _logger.info(
                "KPI CUMUL | poste_id=%s : cumul=%.2fh",
                wc_id, cumul
            )

    # ========================================================================
    # ACTION MANUELLE : recalcul à la demande
    # ========================================================================

    @api.model
    def action_recompute_today(self):
        """Recalcul manuel du snapshot du jour (bouton ou shell)."""
        self.cron_compute_daily_snapshot()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Snapshot recalculé'),
                'message': _('Le snapshot du jour a été recalculé avec succès.'),
                'type': 'success',
                'sticky': False,
            }
        }
