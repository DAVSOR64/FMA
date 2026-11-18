# -*- coding: utf-8 -*-

from . import models
from . import wizard
# Declare au manifeste (post_init_hook) : sans cet import, l'installation du
# module sur une base vierge echoue. Sans effet sur une base deja installee.
from .hooks import post_init_hook
