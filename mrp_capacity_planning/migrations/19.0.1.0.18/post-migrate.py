"""Libere les postes de charge des reservations qui les bloquent des mois.

Chaque ordre de travail planifie pose une ligne dans
``resource_calendar_leaves`` : c'est elle qui dit « ce poste est pris a ces
heures ». Odoo s'en sert pour trouver un creneau libre quand il date une
operation, et il les enjambe toutes.

Le module ecrivait les dates des OT sans jamais toucher a cette reservation —
``_force_write_wo_dates_sql`` passe meme directement par SQL. Quand le
planificateur natif reposait une fin de fabrication aberrante, la reservation
restait a cheval sur l'intervalle fautif. Un montage de 4,83 h bloquait son
poste 623 jours.

Mesure sur la staging le 29/10/2026 :

    Montage FMA   621 reservations de plus de 2 jours, la plus longue 623 j
    Usinage FMA   531                                                 242 j
    CU (banc)     471                                                 123 j
    Debit FMA     443                                                 132 j
    Vitrage FMA   437                                                  89 j

Montage etait annonce « sature jusqu'au 10/08/2028 ». La boucle est
auto-entretenue : une reservation trop longue repousse l'operation suivante,
qui pose a son tour une reservation encore plus longue. Entre deux mesures a
deux heures d'intervalle, les OT finissant plus de six mois apres leur debut
sont passes de 261 a 278.

Ce que fait cette migration
---------------------------
Pour chaque OT d'un OF encore vivant dont la fin s'etale sur plus de deux
jours, elle RECALCULE la fin legitime avec la formule du module lui-meme —
duree effective, heures par jour du calendrier du poste, jours ouvres — puis
la repose si la fin stockee la depasse de plus d'un jour.

Pas de seuil arbitraire : c'est la duree de l'operation qui dit ce qu'elle
peut durer. Une operation qui s'etale legitimement sur trois jours n'est pas
touchee, et rien n'est jamais raccourci en-deca de son calcul.

Les deux tables sont ecrites ENSEMBLE, et c'est tout l'objet : la reservation
suit la date de l'OT. C'est ce couplage qui manquait et qui a produit
l'encombrement.

Ecriture en SQL, volontairement : passer par l'ORM relancerait le
planificateur natif, qui irait chercher un creneau libre dans les
reservations qu'on est precisement en train de corriger.

Aucune suppression. On ne touche qu'aux lignes designees par
``mrp_workorder.leave_id`` : les conges du personnel et les indisponibilites
posees par ``mrp_capacity_week`` vivent dans la meme table et ne sont jamais
approchees.

Numero de version : cette migration se joue au franchissement de 19.0.1.0.18.
Pour la rejouer vers PreProd puis main, la renumeroter selon la version que
porte la branche cible — sinon elle ne se declenche pas.
"""
import logging
import math
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)

# Un jour de battement avant de corriger : l'heure de fin depend du calendrier
# du poste, et on ne reecrit pas une ligne pour quelques heures d'ecart.
MARGE = timedelta(days=1)

# En-deca, une reservation ne peut pas etre la cause d'un blocage de plusieurs
# mois : les blocs du retroplanning se comptent en jours ouvres entiers.
SEUIL_JOURS = 2


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute(
        """
        SELECT w.id
          FROM mrp_workorder w
          JOIN mrp_production p ON p.id = w.production_id
         WHERE w.date_start IS NOT NULL
           AND w.date_finished IS NOT NULL
           AND w.date_finished > w.date_start + interval '%s days'
           AND p.state NOT IN ('done', 'cancel')
         ORDER BY w.id
        """ % SEUIL_JOURS
    )
    ids = [ligne[0] for ligne in cr.fetchall()]
    if not ids:
        _logger.info("Reservations de capacite : rien a corriger.")
        return

    _logger.info(
        "Reservations de capacite : %s ordre(s) de travail a examiner.", len(ids))

    corriges = reservations = 0
    for rang, wo in enumerate(env["mrp.workorder"].browse(ids), start=1):
        production = wo.production_id
        poste = wo.workcenter_id
        if not poste or not wo.date_start:
            continue

        calendrier = (poste.resource_calendar_id
                      or production.company_id.resource_calendar_id)
        heures_par_jour = (calendrier.hours_per_day if calendrier else 0) or 7.8
        heures, _ressources = production._get_effective_duration_hours(wo)
        jours = max(1, int(math.ceil(heures / heures_par_jour)))

        debut = fields.Datetime.to_datetime(wo.date_start)
        dernier_jour = debut.date()
        for _jour in range(jours - 1):
            dernier_jour = production._next_working_day(dernier_jour, poste)
        fin = production._evening_dt(dernier_jour, poste)

        if fields.Datetime.to_datetime(wo.date_finished) <= fin + MARGE:
            # Duree plausible : on ne touche pas.
            continue

        cr.execute(
            "UPDATE mrp_workorder SET date_finished = %s WHERE id = %s",
            (fin, wo.id),
        )
        corriges += 1

        if wo.leave_id:
            cr.execute(
                """
                UPDATE resource_calendar_leaves
                   SET date_from = %s, date_to = %s
                 WHERE id = %s
                """,
                (debut, fin, wo.leave_id.id),
            )
            reservations += 1

        if rang % 500 == 0:
            _logger.info("  ... %s/%s examines, %s corriges", rang, len(ids), corriges)

    # Les ecritures sont passees par SQL : le cache de l'ORM ignore tout.
    env.invalidate_all()

    message = (
        "Migration 19.0.1.0.18 : %s ordre(s) de travail examine(s), "
        "%s date(s) de fin corrigee(s), %s reservation(s) de poste liberee(s)"
        % (len(ids), corriges, reservations)
    )
    _logger.info(message)
    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("mrp_capacity_planning", message, __file__, "0", "migrate"),
    )
