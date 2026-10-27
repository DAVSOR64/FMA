# -*- coding: utf-8 -*-
"""iziqo.sync.job devient polymorphe : partner_id est remplace par le couple
(res_model, res_id) pour accueillir les commerciaux a cote des clients.

Les colonnes sont creees et remplies AVANT que l'ORM ne pose la contrainte
NOT NULL des champs requis, sinon la mise a jour echouerait sur les jobs
existants. La colonne partner_id devenue orpheline est laissee en base :
Odoo ne supprime jamais une colonne de lui-meme, et la garder permet de
rejouer la migration en cas de retour arriere.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'iziqo_sync_job' AND column_name = 'partner_id'
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        ALTER TABLE iziqo_sync_job
            ADD COLUMN IF NOT EXISTS res_model varchar,
            ADD COLUMN IF NOT EXISTS res_id integer
        """
    )
    cr.execute(
        """
        UPDATE iziqo_sync_job
           SET res_model = 'res.partner',
               res_id = partner_id
         WHERE partner_id IS NOT NULL
           AND (res_model IS NULL OR res_id IS NULL)
        """
    )
    _logger.info("Iziqo: %s job(s) migré(s) vers (res_model, res_id).", cr.rowcount)

    # Les jobs sans partner_id (impossible en principe, la colonne etait
    # requise) seraient bloquants pour la contrainte NOT NULL : on les annule.
    cr.execute(
        """
        DELETE FROM iziqo_sync_job
         WHERE res_model IS NULL OR res_id IS NULL
        """
    )
    if cr.rowcount:
        _logger.warning("Iziqo: %s job(s) sans cible supprimé(s).", cr.rowcount)
