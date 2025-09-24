{
    "name": "KPI Facturation",
    "version": "17.0.1.0.1",
    "category": "Sales/Reporting",
    "summary": "Facturé & RAF par affaire, mois/semaine de livraison planifiée, filtrable par tags",
    "depends": ["sale_management", "stock", "account"],
    "data": [
        "views/kpi_report_views.xml",
        "views/sale_orders_to_invoice_or_no.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
}
