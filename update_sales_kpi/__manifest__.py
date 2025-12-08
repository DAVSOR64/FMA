# -*- coding: utf-8 -*-
{
    "name": "update_sales_kpi",
    "summary": """
       update Kpis from Sale orders""",
    "description": """
        Update real KPI with the MRP
    """,
    "category": "Uncategorized",
    "version": "17.0.1.0.1",
    # any module necessary for this one to work correctly
    "depends": ["base", "sale", "mrp", "custom"],
    # always loaded
    "data": [
        # 'security/ir.model.access.csv',
        #'views/views.xml',
        #'views/templates.xml',
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
