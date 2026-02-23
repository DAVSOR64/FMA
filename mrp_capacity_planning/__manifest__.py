# -*- coding: utf-8 -*-
{
    'name': 'MRP Capacity Planning',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing/Planning',
    'summary': 'Planification de capacité hebdomadaire par ressource et poste de travail',
    'description': """
        Gestion de la capacité hebdomadaire des ressources sur les postes de travail.

        Fonctionnalités :
        - Affectation d'une ressource (employé) à un poste de travail
        - Vue Gantt semaine par semaine (1 ligne = 1 ressource)
        - Capacité standard calculée depuis le calendrier de travail
        - Override manuel par semaine (inline ou formulaire)
        - Déduction automatique : jours fériés société, congés validés, arrêts maladie
        - Wizard de génération en masse sur un horizon
        - Recalcul quotidien automatique
        - Standalone : aucune dépendance à mrp_macro_planning
    """,
    'author': 'Clair de Baie',
    'depends': [
        'mrp',
        'hr_holidays',
        'web_gantt',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/mrp_capacity_cron.xml',
        'views/mrp_capacity_resource_views.xml',
        'views/mrp_capacity_week_views.xml',
        'views/mrp_capacity_week_gantt.xml',
        'views/menu.xml',
        'wizard/generate_weeks_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mrp_capacity_planning/static/src/css/capacity.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
