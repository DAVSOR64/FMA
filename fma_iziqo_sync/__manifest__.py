# -*- coding: utf-8 -*-
{
    "name": "Iziqo: synchronisation des clients",
    "summary": "Pousse les sociétés clientes ayant un SIRET vers l'API REST Iziqo (POST / PATCH)",
    "description": """
        Synchronise une fiche client (res.partner) vers l'API REST de
        l'application Iziqo des sa creation ou sa modification, sans attendre
        l'export quotidien. POST a la creation, PATCH a la modification.
        Seules les societes ayant un SIRET sont concernees.

        - file d'attente (iziqo.sync.job) avec relances et journal des envois ;
        - envoi juste apres le commit de la transaction, donc jamais bloquant
          pour l'utilisateur qui enregistre la fiche ;
        - cron de rattrapage pour les envois en echec ;
        - bouton "Synchroniser avec Iziqo" sur la fiche client pour rattraper
          les clients historiques ;
        - perimetre, URL, identifiant de ressource et authentification
          parametrables dans les Parametres.
    """,
    "author": "JBS",
    "version": "19.0.1.0.1",
    "category": "Sales/CRM",
    "license": "LGPL-3",
    "depends": ["base", "contacts", "account", "hr", "custom"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/iziqo_sync_job_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    # Module conserve UNIQUEMENT le temps de le desinstaller proprement des
    # bases ou il l'est encore. Voir DOC_IZIQO_SYNC.md. A supprimer ensuite.,
    "application": False,
}
