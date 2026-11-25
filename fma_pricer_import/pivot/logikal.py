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
import re
import sqlite3

from .schema import Bar, Component, Cut, Lot, Menuiserie, Operation, Quotation

#: Nom donne au lot regroupant les positions hors lot (eco-contribution,
#: lignes de texte...). LOGIKAL leur laisse une phase sans nom.
LOT_SANS_NOM = "SANS LOT"

#: DEUX ECRITURES DU SUFFIXE DE LOT, DEUX TRAITEMENTS.
#:
#: « REP A LOT 1 » : le mot LOT est ecrit. Il ne peut rien designer d'autre
#: que le lot, et le repere est tout ce qui le precede — « REP A ». On coupe
#: sans condition, quel que soit le numero : « REP A LOT 2 » rencontre dans le
#: lot 1 reste le repere « REP A », il n'est pas reparti autrement.
#:
#: « A_1 » : LOGIKAL pose ce suffixe nu lui-meme quand il repartit une
#: position. Il est AMBIGU — « PORTE_2 » est un nom de position parfaitement
#: legitime — et on ne le retire que s'il porte le numero du lot courant.
#:
#: Le mot LOT exige un separateur devant lui, sans quoi « BALLOT1 » serait
#: tronque en « BAL ».
LOT_MOT_RE = re.compile(r"[\s_\-]+LOT[\s_\-]*\d*$", re.IGNORECASE)
LOT_SUFFIX_RE = re.compile(r"_(\d+)$")


def base_position(name, phase):
    """Position independante du lot.

    Les references d'article doivent designer *ce qui est fabrique*, pas le
    lot dans lequel il l'est : une meme menuiserie repartie sur cinq lots
    reste un seul article, une seule nomenclature et une seule ligne de devis.
    C'est ce qui regroupe « REP A LOT 1 » et « REP A LOT 2 » sous le repere
    « REP A », sur une ligne de commande unique.

    Doit rester aligne sur l'autre copie — ``sqlite_connector.base_position``
    nomme les articles, ``logikal.base_position`` nomme les positions du
    pivot : si les deux divergent, la ligne fusionnee du devis ne retrouve
    plus l'article que le connecteur a cree.
    """
    name = (name or "").strip()
    # Le mot LOT d'abord : il est sans ambiguite, et il peut masquer un
    # suffixe nu (« A_1 LOT 2 »).
    coupe = LOT_MOT_RE.search(name)
    if coupe:
        return name[: coupe.start()].strip()
    found = LOT_SUFFIX_RE.search(name)
    if not found:
        return name
    numbers = re.findall(r"\d+", phase or "")
    if numbers and numbers[-1] == found.group(1):
        return name[: found.start()]
    return name


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


#: Correspondance ``LabourTimes.TimeType`` -> poste de charge, telle que
#: ``sqlite_connector`` la pose sur la nomenclature de projet. La sequence
#: reproduit l'ordre de l'atelier.
#:
#: UNE TABLE PAR SITE : LOGIKAL donne le meme numero a des travaux
#: differents d'un atelier a l'autre. Le 11 est du montage chez FMA, du
#: remontage chez F2M ; le 10, vitrage chez FMA, est du remontage chez F2M —
#: ou le vitrage ne se pose pas en atelier. Lire une affaire F2M avec la
#: table FMA fabriquait un vitrage qui n'existe pas, et perdait le debit du
#: 12, que FMA n'emploie pas.
#:
#: Doit rester aligne sur
#: ``sqlite_connector.models.sqlite_connector.POSTES_PAR_TIMETYPE``.
TIME_TYPES = {
    0: ("Debit", 10),
    5: ("CU (banc)", 20),
    4: ("Usinage", 30),
    6: ("Montage", 40),
    11: ("Montage", 40),
    10: ("Vitrage", 50),
}

TIME_TYPES_F2M = {
    0: ("Debit", 10),
    12: ("Debit", 10),
    4: ("Usinage", 30),
    5: ("Usinage", 30),
    6: ("Assemblage", 60),
    10: ("Remontage", 70),
    11: ("Remontage", 70),
}


def time_types(site):
    """La table des temps du site qui a chiffre."""
    return TIME_TYPES_F2M if (site or "").strip().upper() == "F2M" else TIME_TYPES


def _operations(con, menuiseries, site=""):
    """Temps de main d'oeuvre par menuiserie, pour un exemplaire.

    ``LabourTimes.TotalMinutes`` est le temps d'un exemplaire ; le connecteur
    le multiplie par ``Elevations.Amount`` pour totaliser l'affaire. Une
    nomenclature raisonne a l'unite : on garde le temps unitaire.

    Le SITE choisit la table des TimeType : les deux ateliers ne nomment pas
    le meme travail avec le meme numero. cf. ``time_types``.
    """
    table = time_types(site)
    agg = {}
    for eid, minutes, time_type in con.execute(
        "select ElevationId, TotalMinutes, TimeType from LabourTimes"
    ):
        entry = table.get(time_type)
        if entry is None or eid not in menuiseries:
            continue
        name, sequence = entry
        key = (eid, name)
        agg[key] = (agg.get(key, (0.0, sequence))[0] + (minutes or 0.0), sequence)

    for (eid, name), (minutes, sequence) in agg.items():
        if minutes <= 0:
            continue
        menuiseries[eid].operations.append(
            Operation(name=name, minutes=minutes, sequence=sequence)
        )
    for men in menuiseries.values():
        men.operations.sort(key=lambda o: (o.sequence, o.name))


def teinte_profile(site, outer, inner, internal, color):
    """Teinte d'un PROFILE, qui n'obeit pas tout a fait a celle d'un article.

    Chez F2M, sqlite_connector force la teinte a vide sur les profiles — et
    sur eux seuls, la meme ligne etant commentee dans le bloc des articles.
    Les profiles y sont donc crees sans teinte.

    Ne pas reproduire cette exception revenait a chercher un profile « en
    7016 » quand il existe sans teinte : la reference est bonne, la teinte ne
    l'est pas, et l'import annonce un article introuvable ou le trouve dans
    une autre teinte.
    """
    if (site or "").strip().upper() == "F2M":
        return ""
    return color_of(outer, inner, internal, color)


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


def parse(path, source=None, site_defaut=""):
    """Lit un export LOGIKAL et renvoie un :class:`~.schema.Quotation`."""
    con = _connect(path)
    try:
        return _parse(con, source or os.path.basename(path), site_defaut)
    finally:
        con.close()


def _site(con):
    """Site qui a chiffre, lu dans les parametres du poste LOGIKAL.

    ``REPORTVARIABLES`` porte, sous le noeud « Addresses », l'adresse de
    l'entreprise qui edite les documents : ``OwnAddress01`` vaut « FMA » ou
    « F2M », ``OwnAddress06`` donne la ville. C'est le seul endroit du
    fichier qui distingue les deux ateliers — ni le projet, ni la phase, ni
    la menuiserie ne le portent.

    Ce site departage les postes de charge homonymes : « Debit FMA » et
    « Debit F2M » existent tous deux dans Odoo.
    """
    try:
        row = con.execute(
            "select SValue from REPORTVARIABLES"
            " where SubNode = 'Addresses' and FieldName = 'OwnAddress01'"
            " limit 1"
        ).fetchone()
    except Exception:
        # Table absente d'un export ancien : on continue sans site plutot que
        # de faire echouer tout l'import pour un poste de charge.
        return ""
    return (row[0] or "").strip() if row else ""


def _profils_connus(con):
    """Les codes que LOGIKAL declare PROFILES pour cette affaire.

    « AllProfiles » est la liste des profiles de l'affaire, et elle fait foi.
    Les tables « Profiles » et « ProfileBars », elles, portent tout ce que le
    logiciel DECOUPE : les profiles, mais aussi les articles livres en
    longueur — plaques d'isolation, inserts coupe-feu, joints a bourrer. Rien,
    dans ces deux tables, ne les distingue.

    Mesure faite sur A25-10-09731 : douze barres pour DEUX profiles seulement
    (W1311073, W3090200, les deux seuls presents dans AllProfiles). Les dix
    autres barres sont trois articles — W4090033, W4090037, W4090112 — que
    AllArticles compte par ailleurs, au metre, et qui n'apparaissent dans
    aucun AllProfiles. Faute de ce depart, ces trois articles partaient sur la
    table de debit, ou personne ne les scie, et manquaient au casier.

    Un ensemble VIDE ne filtre rien : un fichier sans cette table verrait
    sinon tout son debit disparaitre.
    """
    try:
        lignes = con.execute("select ArticleCode_Number from AllProfiles")
    except Exception:  # noqa: BLE001 — table absente : on ne filtre pas
        return frozenset()
    return frozenset(
        (code or "").strip() for (code,) in lignes if (code or "").strip()
    )


#: De quoi ramener une taille a des millimetres. Le fichier exprime les
#: longueurs dans l'unite que l'utilisateur a choisie, et elle varie d'une
#: colonne a l'autre DANS LA MEME TABLE : ProfileBars.Length vient en mm,
#: AllProfiles.Length en m.
_VERS_MM = {"mm": 1.0, "cm": 10.0, "dm": 100.0, "m": 1000.0}


def _mm(brut, sortie, unite):
    """Une longueur en millimetres, quelle que soit l'unite d'AFFICHAGE.

    Le fichier porte chaque longueur deux fois : la colonne brute, toujours en
    metres, et la colonne « _Output » exprimee dans l'unite que l'utilisateur
    a choisie — « _Unit ». Lire la seconde en supposant des millimetres marche
    sur les dix-huit exports releves, ou Profiles.Length_Unit vaut « mm » sans
    exception. Mais c'est un REGLAGE D'AFFICHAGE, pas une loi : un export en
    metres ferait lire 2,19 mm la ou il y a 2,19 m, et personne ne verrait
    rien — le debit serait simplement mille fois trop petit.

    On lit donc l'unite a cote de la valeur, et la colonne brute sert de
    recours quand elle manque.
    """
    facteur = _VERS_MM.get((unite or "").strip().lower())
    if facteur and sortie is not None:
        return sortie * facteur
    return (brut or 0.0) * 1000.0


def _unites_declarees(con):
    """L'unite de mesure que le fichier donne a chaque reference.

    C'EST LA DONNEE QUI MANQUAIT, et elle etait ecrite depuis le debut.
    AllProfiles.Units_Unit vaut « m » sur les 111 profiles des dix-huit
    exports releves : un profile se mesure en metres, le fichier le dit, et
    il n'y a rien a deduire. AllArticles.Units_Unit, lui, departage « pce »
    (382 fois) et « m » (75 fois) : c'est lui qui dit si un article se compte
    en pieces ou en longueur, la ou le moteur le devinait au fait que LOGIKAL
    l'avait decoupe.
    """
    unites = {}
    for table in ("AllArticles", "AllProfiles"):
        try:
            lignes = con.execute(
                "select ArticleCode_Number, Units_Unit from %s" % table
            ).fetchall()
        except Exception:  # noqa: BLE001 — table absente
            continue
        for code, unite in lignes:
            code = (code or "").strip()
            unite = (unite or "").strip().lower()
            if code and unite:
                unites[code] = unite
    return unites


def _longueurs_unitaires(con):
    """La longueur d'UNE piece d'article, par reference, en mm.

    LA CONVERSION PIECE <-> METRE, ET ELLE EST DANS LE FICHIER. Les articles
    livres en longueur que LOGIKAL decoupe sans les declarer profiles
    (plaques d'isolation, inserts) sont comptes en METRES dans
    AllArticles.Units — 4,592 pour les six coupes de W4090033 — alors
    qu'Odoo les tient en pieces. Il manquait de quoi passer de l'un a
    l'autre, et le besoin devenait inexprimable.

    AllArticles.Length le donne : 1,2 m pour W4090033, dont la designation
    dit « 12x26x1200 mm », 1,2 m aussi pour W4090037, « L=120 ». Le nombre de
    pieces, c'est le besoin en metres divise par cette longueur.

    Pas AllProfiles : la longueur d'un profile n'a rien d'unitaire, c'est
    celle de sa barre, et un profile se compte en metres de toute facon.
    """
    longueurs = {}
    try:
        lignes = con.execute(
            "select ArticleCode_Number, Length, Length_Output, Length_Unit"
            " from AllArticles").fetchall()
    except Exception:  # noqa: BLE001 — table ou colonne absente
        return longueurs
    for code, brut, sortie, unite in lignes:
        code = (code or "").strip()
        if not code:
            continue
        taille = _mm(brut, sortie, unite)
        if taille > 0:
            longueurs[code] = taille
    return longueurs


def _conditionnements(con):
    """Ce qu'UNE unite d'achat contient de longueur, par reference, en mm.

    « PUSize » : la taille du conditionnement. Pour un profile ordinaire elle
    vaut 1 m — il se vend au metre — et n'a donc rien a voir avec la longueur
    de ses barres. Pour un article vendu en longueur FIXE, en revanche, elle
    est la seule donnee qui dise sa taille : le tube « Lg 2.5ml » de
    A26-11-10280 porte PUSize = 2,5 m, IsSpecialLength = 1, et LOGIKAL ne lui
    fait aucun plan de coupe — aucune ligne dans ProfileBars. Sans PUSize, son
    besoin de debit n'est exprimable ni en metres ni en barres, et le lot
    remonte un manque que personne ne peut lever.

    ON EXIGE L'UNITE. AllProfiles porte PUSize sans PUSize_Unit (mesure faite
    sur l'affaire ci-dessus : la colonne y est vide pour les dix profiles),
    et un nombre sans unite ne se convertit pas. AllArticles, lui, la porte :
    c'est de la que vient la valeur exploitable. Une taille sans unite est
    ignoree plutot que supposee en metres.
    """
    tailles = {}
    for table in ("AllArticles", "AllProfiles"):
        try:
            lignes = con.execute(
                "select ArticleCode_Number, PUSize, PUSize_Unit from %s"
                % table).fetchall()
        except Exception:  # noqa: BLE001 — table ou colonne absente
            continue
        for code, taille, unite in lignes:
            code = (code or "").strip()
            facteur = _VERS_MM.get((unite or "").strip().lower())
            if code and taille and facteur:
                tailles[code] = taille * facteur
    return tailles


def _parse(con, source, site_defaut=""):
    quo = Quotation(pricer="logikal", source=source)

    row = con.execute(
        "select Name, OfferNo, OrderNo from Projects limit 1"
    ).fetchone()
    if row:
        quo.project = {"name": row[0] or "", "offer_no": row[1] or "",
                       "order_no": row[2] or ""}

    # A DEFAUT DE SITE DANS LE FICHIER, CELUI QUE L'APPELANT CONNAIT.
    # REPORTVARIABLES manque a beaucoup d'exports — le site y est vide sur
    # les fichiers releves — et le site ne departage pas seulement les postes
    # de charge homonymes : il choisit la TABLE DES TEMPS. Lire une affaire
    # F2M avec la table FMA lui fabrique un vitrage qu'elle n'a pas.
    quo.site = _site(con) or (site_defaut or "")

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
        lot_ref = lots[pid].ref if pid in lots else ""
        men = Menuiserie(
            ref=(name or "").strip(),
            position=base_position(name, lot_ref),
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
        eid, code, ref_fichier, base_code, code_supplier, desc, units, unit,
        price, sid, internal, color,
    ) in con.execute(
        """select i.ElevationId, a.ArticleCode_Number, a.ArticleCode,
                  a.ArticleCode_BaseNumber, a.ArticleCode_Supplier,
                  a.Description,
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
                ref_fichier=(ref_fichier or "").strip(),
                base_code=(base_code or "").strip(),
                code_supplier=(code_supplier or "").strip(),
                description=(desc or "").strip(),
                qty=units or 0.0,
                uom=(unit or "").strip(),
                supplier=suppliers.get(sid, ""),
                color=color_of("", "", internal, color),
                price=price or 0.0,
            )
        )

    # --- composants : vitrage ------------------------------------------------
    # Info2 EST LU ICI, et pas seulement par le connecteur historique. C'est
    # le champ ou le deviseur ecrit CHARIOT ou PALETTE, et c'est lui qui
    # decide si le vitrage se commande avec son lot (atelier) ou pour
    # l'affaire entiere (chantier). Sans lui, tout le remplissage importe par
    # le pricer restait sans destination.
    for eid, name, desc, width, height, price, sid, info2, nature in con.execute(
        """select i.ElevationId, g.Name, g.Description,
                  g.Width_Output, g.Height_Output, g.Price, g.LK_SupplierId,
                  g.Info2, g.AreaOffer
             from Glass g
             join Insertions i on i.InsertionID = g.InsertionId"""
    ):
        # AreaOffer DIT CE QU'EST LE REMPLISSAGE. La table Glass porte le
        # vitrage (« Glass ») mais aussi les panneaux (« Panels »), et la
        # destination ne se decide que pour le vitrage : un panneau est
        # systematiquement pose en atelier. On impose donc CHARIOT sans lire
        # Info2, comme le fait le connecteur historique — les deux lecteurs
        # du meme fichier doivent dire la meme chose.
        if (nature or "").strip() != "Glass":
            info2 = "CHARIOT"
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
                info_livraison=(info2 or "").strip(),
            )
        )

    # --- debit : les coupes de profiles, par exemplaire ----------------------
    profils = _profils_connus(con)
    #: Ce que LOGIKAL coupe sans que ce soit un profile : {code: description}.
    reclasses = {}
    for (
        eid, code, ref_fichier, base_code, code_supplier, desc,
        length_sortie, length_unite, length_brute,
        amount, sid, outer, inner, internal, color,
    ) in con.execute(
        """select i.ElevationId, p.ArticleCode_Number, p.ArticleCode,
                  p.ArticleCode_BaseNumber, p.ArticleCode_Supplier,
                  p.Description,
                  p.Length_Output, p.Length_Unit, p.Length,
                  p.Amount, p.LK_SupplierID,
                  p.OuterColorInfoInternal, p.InnerColorInfoInternal,
                  p.ColorInfoInternal, p.Color
             from Profiles p
             join Insertions i on i.InsertionID = p.InsertionId"""
    ):
        men = menuiseries.get(eid)
        if men is None:
            continue
        code_net = (code or "").strip()
        length = _mm(length_brute, length_sortie, length_unite)
        if profils and code_net not in profils:
            # COUPE, MAIS PAS UN PROFILE. L'article part avec la
            # quincaillerie, dans la LONGUEUR que ses coupes totalisent :
            # c'est ainsi que LOGIKAL lui-meme le compte dans AllArticles
            # (Units = 4,592 m pour W4090033, soit exactement ses 4 592 mm de
            # coupes). Il rejoint donc les joints et bandes livres en
            # longueur, que le fichier ne fait pas passer par le debit.
            reclasses.setdefault(code_net, (desc or "").strip())
            men.components.append(
                Component(
                    kind="article",
                    code=code_net,
                    ref_fichier=(ref_fichier or "").strip(),
                    base_code=(base_code or "").strip(),
                    code_supplier=(code_supplier or "").strip(),
                    description=(desc or "").strip(),
                    supplier=suppliers.get(sid, ""),
                    color=teinte_profile(
                        quo.site, outer, inner, internal, color),
                    qty=amount or 1.0,
                    length_mm=length or 0.0,
                )
            )
            continue
        men.debit.append(
            Cut(
                code=(code or "").strip(),
                ref_fichier=(ref_fichier or "").strip(),
                base_code=(base_code or "").strip(),
                code_supplier=(code_supplier or "").strip(),
                description=(desc or "").strip(),
                supplier=suppliers.get(sid, ""),
                color=teinte_profile(quo.site, outer, inner, internal, color),
                length_mm=length or 0.0,
                qty=amount or 1.0,
            )
        )

    # --- operations : temps de main d'oeuvre par menuiserie ------------------
    _operations(con, menuiseries, quo.site)

    if reclasses:
        quo.warnings.append(
            "%d article(s) livre(s) en longueur sont ranges avec la "
            "QUINCAILLERIE et non avec le debit : %s. LOGIKAL les decoupe "
            "comme des barres, mais AllProfiles ne les declare pas profiles."
            % (
                len(reclasses),
                ", ".join(
                    "%s (%s)" % (code, desc) if desc else code
                    for code, desc in sorted(reclasses.items())
                ),
            )
        )

    # --- barres : rattachement au lot, via les coupes ------------------------
    _attach_bars(con, quo, lots, suppliers, profils)
    quo.conditionnements = _conditionnements(con)
    quo.unites = _unites_declarees(con)
    quo.longueurs_unitaires = _longueurs_unitaires(con)

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
                # EN LONGUEUR POUR CE QUI SE COUPE. LOGIKAL compte ces
                # articles-la en METRES dans AllArticles.Units — 4,592 pour
                # les 4 592 mm de coupes de W4090033 —, pas en nombre de
                # pieces. Comparer six coupes a 4,592 m faisait echouer la
                # reconciliation sur un faux ecart.
                quantite = comp.qty
                if getattr(comp, "length_mm", 0.0):
                    quantite = comp.qty * comp.length_mm / 1000.0
                ventile[comp.code] = (
                    ventile.get(comp.code, 0.0) + quantite * men.qty)

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


def _attach_bars(con, quo, lots, suppliers, profils=frozenset()):
    """Rattache chaque barre a son lot et controle qu'elle n'en sert qu'un.

    Les barres qui ne sont pas des PROFILES sont ecartees : ce sont les
    articles livres en longueur, deja comptes avec la quincaillerie (cf.
    _profils_connus). Les laisser ici les faisait sortir du magasin comme des
    barres, pour la table de debit.

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
        bar_id, code, base_code, ref_fichier, code_supplier, desc,
        length_sortie, length_unite, length_brute,
        used_sortie, used_unite, used_brute,
        amount, sid,
        outer, inner, internal, color,
    ) in con.execute(
        """select ProfileBarID, ArticleCode_Number, ArticleCode_BaseNumber,
                  ArticleCode, ArticleCode_Supplier,
                  Description,
                  Length_Output, Length_Unit, Length,
                  UsedLength_Output, UsedLength_Unit, UsedLength,
                  Amount, SupplierId,
                  OuterColorInfoInternal, InnerColorInfoInternal,
                  ColorInfoInternal, Color
             from ProfileBars"""
    ):
        if profils and (code or "").strip() not in profils:
            continue
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
                ref_fichier=(ref_fichier or "").strip(),
                base_code=(base_code or "").strip(),
                code_supplier=(code_supplier or "").strip(),
                description=(desc or "").strip(),
                supplier=suppliers.get(sid, ""),
                color=teinte_profile(quo.site, outer, inner, internal, color),
                length_mm=_mm(length_brute, length_sortie, length_unite),
                used_mm=_mm(used_brute, used_sortie, used_unite),
                qty=amount or 1.0,
            )
        )

    if orphans:
        quo.warnings.append(
            "%d barre(s) sans coupe rattachable a une menuiserie (profile "
            "saisi manuellement ou longueur speciale) : a reprendre a la main."
            % orphans
        )
