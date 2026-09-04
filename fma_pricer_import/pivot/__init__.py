# -*- coding: utf-8 -*-
"""Format pivot des chiffrages et adaptateurs par pricer.

Ce sous-paquet ne depend pas d'Odoo : il transforme un fichier de pricer
(LOGIKAL sqlite, TechDesign XML) en une structure Python unique, verifiable
hors base. C'est ce pivot que le moteur d'import consomme ensuite pour creer
le devis, les articles et les nomenclatures.
"""
from . import schema
from . import logikal
from . import techdesign_order
