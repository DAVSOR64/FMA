# -*- coding: utf-8 -*-
"""Adaptateur LOGIKAL : export sqlite -> format pivot.

Points cles constates sur les exports reels :

* le **lot** existe nativement dans le fichier : table ``Phases``, rattachee
  aux menuiseries par ``Elevations.ElevationGroupId -> ElevationGroups.PhaseId``.
  Il n'y a donc rien a ressaisir ;
* le **debit reel** est dans ``ProfileCuts`` (une ligne par piece coupee),
  relie a la menuiserie par ``Profiles -> Insertions -> Elevations``. Le champ
  ``AllProfiles.Amount``, seul lu historiquement, n'en donne que l'agregat et
  perd le plan de coupe ;
* les **barres** sont dans ``ProfileBars``. Attention : un export d'affaire
  entiere reoptimise au niveau projet meme si les debits ont ete faits par
  lot. Une barre porte alors des coupes de plusieurs lots et ses quantites ne
  sont exploitables ni en achat ni en production — c'est ce que detecte
  ``bars_per_lot``.

Unites : ``Length`` est en metres, ``Length_Output`` en millimetres. On ne lit
que les champs ``_Output`` pour rester en mm.
"""
import os
import sqlite3

from .schema import Bar, Component, Cut, Lot, Menuiserie, Quotation

#: Nom donne au lot regroupant les positions hors lot (eco-contribution,
#: lignes de texte...). LOGIKAL leur laisse une phase sans nom.
LOT_SANS_NOM = "SANS LOT"


def _connect(path):
    """Ouverture en lecture seule : on ne modifie jamais le fichier du pricer."""
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


def color_of(outer, inner, internal, color):
    """Teinte d'un article, telle que ``sqlite_connector`` la construit.

    Le connecteur cree **un article par reference et par teinte** : le
    ``default_code`` est suffixe par la couleur et ``x_studio_color_logikal``
    la porte. Retrouver un article sur la seule reference ne suffit donc pas —
    d'ou la reproduction a l'identique de sa regle de resolution.
    """
    def clean(value):
        value = (value or "").strip()
        return "" if value in ("None", " ") else value

    outer, inner = clean(outer), clean(inner)
    if outer and inner:
        return "%s/%s" % (outer, inner)
    couleur = clean(internal)
    if not couleur:
        couleur = clean(color)
        if couleur.lower() == "sans":
            couleur = ""
    return couleur


def _suppliers(con):
    """Libelles fournisseurs par identifiant.

    La table ``Suppliers`` n'a pas de colonne ``Name`` : le libelle est la
    premiere ligne d'adresse renseignee.
    """
    names = {}
    for row in con.execute(
        "select SupplierID, ActiveTitle, Address1, Address2 from Suppliers"
    ):
        sid, title, addr1, addr2 = row
        names[sid] = next(
            (v.strip() for v in (title, addr1, addr2) if v and v.strip()), ""
        )
    return names


def parse(path, source=None):
    """Lit un export LOGIKAL et renvoie un :class:`~.schema.Quotation`."""
    con = _connect(path)
    try:
        return _parse(con, source or os.path.basename(path))
    finally:
        con.close()


def _parse(con, source):
    quo = Quotation(pricer="logikal", source=source)

    row = con.execute(
        "select Name, OfferNo, OrderNo from Projects limit 1"
    ).fetchone()
    if row:
        quo.project = {"name": row[0] or "", "offer_no": row[1] or "",
                       "order_no": row[2] or ""}

    suppliers = _suppliers(con)

    # --- lots et menuiseries -------------------------------------------------
    lots = {}  # PhaseID -> Lot
    for pid, name, guid in con.execute(
        "select PhaseID, Name, xGUID from Phases"
    ):
        lots[pid] = Lot(ref=(name or "").strip() or LOT_SANS_NOM,
                        guid=(guid or "").strip())

    menuiseries = {}  # ElevationID -> (Menuiserie, PhaseID)
    for eid, name, desc, auto, amount, width, height, pid in con.execute(
        """select e.ElevationID, e.Name, e.Description, e.AutoDescription,
                  e.Amount, e.Width_Output, e.Height_Output, eg.PhaseId
             from Elevations e
             join ElevationGroups eg on eg.ElevationGroupID = e.ElevationGroupId
         order by e.ElevationID"""
    ):
        men = Menuiserie(
            ref=(name or "").strip(),
            description=(desc or auto or "").strip(),
            qty=amount or 1.0,
            width_mm=width or 0.0,
            height_mm=height or 0.0,
        )
        menuiseries[eid] = men
        lot = lots.get(pid)
        if lot is None:
            lot = lots[pid] = Lot(ref=LOT_SANS_NOM)
        lot.menuiseries.append(men)

    # --- composants : articles et quincaillerie ------------------------------
    # ``Units`` est la quantite pour UN exemplaire ; la multiplication par
    # ``Elevations.Amount`` reconstitue exactement ``AllArticles.Units``.
    for (
        eid, code, desc, units, unit, price, sid, internal, color,
    ) in con.execute(
        """select i.ElevationId, a.ArticleCode_Number, a.Description,
                  a.Units, a.Units_Unit, a.Price, a.LK_SupplierId,
                  a.ColorInfoInternal, a.Color
             from Articles a
             join Insertions i on i.InsertionID = a.InsertionId"""
    ):
        men = menuiseries.get(eid)
        if men is None:
            continue
        men.components.append(
            Component(
                kind="article",
                code=(code or "").strip(),
                description=(desc or "").strip(),
                qty=units or 0.0,
                uom=(unit or "").strip(),
                supplier=suppliers.get(sid, ""),
                color=color_of("", "", internal, color),
                price=price or 0.0,
            )
        )

    # --- composants : vitrage ------------------------------------------------
    for eid, name, desc, width, height, price, sid in con.execute(
        """select i.ElevationId, g.Name, g.Description,
                  g.Width_Output, g.Height_Output, g.Price, g.LK_SupplierId
             from Glass g
             join Insertions i on i.InsertionID = g.InsertionId"""
    ):
        men = menuiseries.get(eid)
        if men is None:
            continue
        men.components.append(
            Component(
                kind="glass",
                code=(name or "").strip(),
                description=(desc or "").strip(),
                qty=1.0,
                uom="u",
                supplier=suppliers.get(sid, ""),
                price=price or 0.0,
                width_mm=width or 0.0,
                height_mm=height or 0.0,
            )
        )

    # --- debit : les coupes de profiles, par exemplaire ----------------------
    for (
        eid, code, desc, length, amount, sid, outer, inner, internal, color,
    ) in con.execute(
        """select i.ElevationId, p.ArticleCode_Number, p.Description,
                  p.Length_Output, p.Amount, p.LK_SupplierID,
                  p.OuterColorInfoInternal, p.InnerColorInfoInternal,
                  p.ColorInfoInternal, p.Color
             from Profiles p
             join Insertions i on i.InsertionID = p.InsertionId"""
    ):
        men = menuiseries.get(eid)
        if men is None:
            continue
        men.debit.append(
            Cut(
                code=(code or "").strip(),
                description=(desc or "").strip(),
                supplier=suppliers.get(sid, ""),
                color=color_of(outer, inner, internal, color),
                length_mm=length or 0.0,
                qty=amount or 1.0,
            )
        )

    # --- barres : rattachement au lot, via les coupes ------------------------
    _attach_bars(con, quo, lots, suppliers)

    quo.lots = [lot for lot in lots.values() if lot.menuiseries or lot.bars]
    _reconcile(con, quo)
    return quo


#: Tolerance de reconciliation, en unites d'article. Les quantites sont
#: stockees en flottant : on compare a l'arrondi du millieme, pas a l'egalite.
TOLERANCE = 0.01


def _reconcile(con, quo):
    """Verifie que la somme des nomenclatures egale le besoin de l'affaire.

    LOGIKAL publie dans ``AllArticles`` le total consomme par l'affaire. Si la
    ventilation par menuiserie ne le retrouve pas, c'est qu'un article n'est
    rattache a aucune position : l'import serait faux et doit etre refuse.
    """
    besoin = {}
    for code, units in con.execute(
        "select ArticleCode_Number, Units from AllArticles"
    ):
        besoin[(code or "").strip()] = besoin.get((code or "").strip(), 0.0) + (
            units or 0.0
        )

    ventile = {}
    for lot in quo.lots:
        for men in lot.menuiseries:
            for comp in men.components:
                if comp.kind != "article":
                    continue
                ventile[comp.code] = ventile.get(comp.code, 0.0) + comp.qty * men.qty

    ecarts = [
        (code, besoin.get(code, 0.0), ventile.get(code, 0.0))
        for code in sorted(set(besoin) | set(ventile))
        if abs(besoin.get(code, 0.0) - ventile.get(code, 0.0)) > TOLERANCE
    ]
    if ecarts:
        detail = ", ".join(
            "%s (attendu %.3f, ventile %.3f)" % e for e in ecarts[:5]
        )
        if len(ecarts) > 5:
            detail += " et %d autre(s)" % (len(ecarts) - 5)
        quo.warnings.append(
            "Reconciliation des articles en echec sur %d reference(s) : %s. "
            "Le total des nomenclatures ne retrouve pas le besoin de "
            "l'affaire." % (len(ecarts), detail)
        )


def _attach_bars(con, quo, lots, suppliers):
    """Rattache chaque barre a son lot et controle qu'elle n'en sert qu'un.

    Une barre appartient au lot de ses coupes. Si ses coupes relevent de
    plusieurs lots, l'optimisation du fichier est faite au niveau projet : le
    lot n'est plus fabricable seul, et les quantites de barres sont declarees
    inexploitables (``bars_per_lot = False``).
    """
    bar_phases = {}
    for bar_id, pid in con.execute(
        """select pc.ProfileBarId, eg.PhaseId
             from ProfileCuts pc
             join Profiles p on p.ProfileID = pc.LK_ProfileId
             join Insertions i on i.InsertionID = p.InsertionId
             join Elevations e on e.ElevationID = i.ElevationId
             join ElevationGroups eg on eg.ElevationGroupID = e.ElevationGroupId
         group by pc.ProfileBarId, eg.PhaseId"""
    ):
        bar_phases.setdefault(bar_id, set()).add(pid)

    shared = sorted(b for b, phases in bar_phases.items() if len(phases) > 1)
    if shared:
        quo.bars_per_lot = False
        noms = sorted(
            {lots[p].ref for b in shared for p in bar_phases[b] if p in lots}
        )
        quo.warnings.append(
            "Optimisation faite au niveau affaire : %d barres sur %d portent "
            "des coupes de plusieurs lots (%s). Les quantites de barres de ce "
            "fichier ne sont pas exploitables — demandez un export par lot."
            % (len(shared), len(bar_phases), ", ".join(noms))
        )

    orphans = 0
    for (
        bar_id, code, desc, length, used, amount, sid,
        outer, inner, internal, color,
    ) in con.execute(
        """select ProfileBarID, ArticleCode_Number, Description,
                  Length_Output, UsedLength_Output, Amount, SupplierId,
                  OuterColorInfoInternal, InnerColorInfoInternal,
                  ColorInfoInternal, Color
             from ProfileBars"""
    ):
        phases = bar_phases.get(bar_id) or set()
        if len(phases) != 1:
            # Barre non rattachable (saisie manuelle, longueur speciale) ou
            # partagee : on ne l'affecte a aucun lot.
            if not phases:
                orphans += 1
            continue
        lot = lots.get(next(iter(phases)))
        if lot is None:
            orphans += 1
            continue
        lot.bars.append(
            Bar(
                code=(code or "").strip(),
                description=(desc or "").strip(),
                supplier=suppliers.get(sid, ""),
                color=color_of(outer, inner, internal, color),
                length_mm=length or 0.0,
                used_mm=used or 0.0,
                qty=amount or 1.0,
            )
        )

    if orphans:
        quo.warnings.append(
            "%d barre(s) sans coupe rattachable a une menuiserie (profile "
            "saisi manuellement ou longueur speciale) : a reprendre a la main."
            % orphans
        )
