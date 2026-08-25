# -*- coding: utf-8 -*-
"""Désactive l'automatisation Studio qui vidait l'acheteur des commandes d'achat.

L'automatisation « DSA : Mise à jour du responsable PO par le responsable
PROJECT » (base.automation, déclencheur on_create_or_write) exécute :

    if record.x_studio_projet_du_so and record.x_studio_projet_du_so.user_id:
        record.write({'user_id': record.x_studio_projet_du_so.user_id.id})
    else :
        record.write({'user_id' : False})

La branche `else` s'applique à la création *et* à chaque sauvegarde : elle
écrasait le défaut standard du champ `purchase.order.user_id` (l'utilisateur
courant), obligeant les acheteurs à ressaisir leur nom sur chaque commande
alors que la quasi-totalité d'entre elles n'ont pas de « Projet du SO ».

La règle est déjà portée en Python dans
`fma_custom/models/purchase_order.py::_sync_responsible_from_project`, qui
conserve la propagation du responsable de projet sans jamais vider le champ.
L'automatisation en base fait donc double emploi : on la désactive.
"""
from odoo import api, SUPERUSER_ID

# Marqueur présent uniquement dans le code de cette automatisation : les autres
# règles Studio sur purchase.order ("DSA Reference compute PO", propagation
# analytique) lisent bien x_studio_projet_du_so et user_id, mais aucune
# n'affecte `x_studio_projet_du_so.user_id.id`.
_CODE_MARKER = "x_studio_projet_du_so.user_id.id"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    actions = env["ir.actions.server"].search([
        ("model_id.model", "=", "purchase.order"),
        ("state", "=", "code"),
        ("code", "ilike", _CODE_MARKER),
    ])
    automations = actions.mapped("base_automation_id").filtered("active")
    if not automations:
        return

    automations.write({"active": False})
    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("fma_custom",
         "Migration 19.0.1.0.8: désactivé %s automatisation(s) Studio %s"
         " (responsable PO depuis le projet, déjà portée en Python)"
         % (len(automations), automations.ids),
         __file__, "0", "migrate"),
    )
