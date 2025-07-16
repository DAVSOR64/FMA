from . import stock_picking
from . import delivery_service_rate_monthly
from odoo import api, SUPERUSER_ID

def pre_init_hook(cr):
    with open('delivery_service_rate/data/delivery_service_rate_view.sql', 'r') as f:
        cr.execute(f.read())
      
