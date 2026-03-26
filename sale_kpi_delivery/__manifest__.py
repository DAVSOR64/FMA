{
    "name": "KPI Facturation / Appro / Stock",
    "version": "17.0.2.0.0",
    "category": "Sales/Reporting",
    "summary": (
        "KPI par affaire : Vente facturée & RAF, "
        "Appro (non livrées, livrées non facturées, livrées facturées), "
        "Stock consommé via nomenclature MRP."
    ),
    "depends": ["sale_management", "stock", "account", "purchase", "mrp"],
    "data": [
        "views/kpi_report_views.xml",
        "views/sale_orders_to_invoice_or_no.xml",
        "views/sale_to_invoice_ht_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "auto_install": False,
}
