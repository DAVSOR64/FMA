# -*- coding: utf-8 -*-
{
    "name": "Iziqo: synchronisation clients et commerciaux",
    "summary": "Pousse les clients et les commerciaux vers l'API REST Iziqo (POST / PATCH)",
    "description": """
        Synchronise les fiches Odoo vers l'API REST de l'application Iziqo
        des leur creation ou leur modification, sans attendre l'export
        quotidien. POST a la creation, PATCH a la modification.

        Deux ressources :
        - les clients (res.partner) : societes ayant un SIRET ;
        - les commerciaux (hr.employee) : employes du departement commercial.

        - file d'attente (iziqo.sync.job) avec relances et journal des envois ;
        - envoi juste apres le commit de la transaction, donc jamais bloquant
          pour l'utilisateur qui enregistre la fiche ;
        - cron de rattrapage pour les envois en echec ;
        - bouton "Synchroniser avec Iziqo" sur la fiche client et sur la fiche
          employe pour rattraper les fiches historiques ;
        - perimetre, URL, identifiant de ressource et authentification
          parametrables dans les Parametres.
    """,
    "author": "JBS",
    # 1.1.0 : les commerciaux (hr.employee) sont synchronises comme les clients.
    # La file d'attente devient polymorphe (res_model, res_id) -- migration
    # dans migrations/19.0.1.1.0/pre-migrate.py.
    "version": "19.0.1.1.0",
    "category": "Sales/CRM",
    "license": "LGPL-3",
    "depends": ["base", "contacts", "account", "hr", "custom"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/iziqo_sync_job_views.xml",
        "views/res_partner_views.xml",
        "views/hr_employee_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
