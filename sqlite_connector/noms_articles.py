# -*- coding: utf-8 -*-
"""Le nom des articles de menuiserie, et celui de leurs nomenclatures.

Le connecteur nommait l'article d'une menuiserie d'apres Elevations.Description
et rien d'autre. Quand le chiffreur laisse ce champ vide dans LOGIKAL, l'article
naissait avec sa reference mais SANS NOM. Or Odoo n'affiche rien pour un modele
d'article sans nom -- pas meme sa reference : la liste des nomenclatures montre
alors une ligne blanche, et c'est de la que viennent les « nomenclatures sans
nom ».

La regle, la meme a la creation, au reimport et a la reprise :

* le nom de l'article est la DESIGNATION -- premiere ligne non vide de la
  description de la ligne de commande, debarrassee de la reference entre
  crochets qu'Odoo y prefixe. La reference reste dans default_code : l'ecran
  affiche « [reference] designation » ;
* l'import n'ecrit le nom que s'il lui appartient encore : nom vide, ou egal a
  la derniere valeur qu'il a lui-meme posee (fma_nom_importe). Un nom saisi a la
  main, meme absurde, n'est jamais ecrase : il est signale ;
* le nom est ecrit dans TOUTES les langues installees. Le champ est traduisible
  (jsonb, une cle par langue) : ecrit dans une seule, il resterait vide dans
  l'ecran des utilisateurs d'une autre.

Ce fichier ne depend que de l'ORM standard : la reprise (migration) et le
script de console l'emploient tel quel, y compris sur une base ou le champ
fma_nom_importe n'existe pas encore.

Aucune ligne vide a l'interieur des fonctions : le meme texte doit pouvoir
etre colle dans une console Python.
"""
import logging
import re

_logger = logging.getLogger(__name__)

# Suffixe de reference -> (nom, code de nomenclature, ancien nom pose par
# l'import avant cette regle).
SEMI_FINIS = {
    "DEB": ("Débit – %s", "%s – Débit", "%s - debite"),
    "QUI": ("Quincaillerie – %s", "%s – Quincaillerie", "%s - kit quincaillerie"),
}

_CROCHETS = re.compile(r"^\s*\[[^\]]*\]\s*")


def designation_ligne(texte, reference=""):
    """Designation portee par une description de ligne de commande.

    Premiere ligne qui dit quelque chose : la reference entre crochets est
    retiree, et une ligne qui ne porte QUE la reference ne compte pas.
    """
    reference = (reference or "").strip().upper()
    for ligne in (texte or "").splitlines():
        ligne = _CROCHETS.sub("", ligne).strip()
        # La reference ecrite sans crochets, seule ou suivie d'un separateur.
        # Jamais un simple debut de mot : la reference « A » ne doit pas
        # amputer « Armoire ».
        suite = ligne[len(reference):]
        if reference and ligne.upper().startswith(reference) and (
                not suite or suite[0] in " :–-"):
            ligne = suite.strip(" -–:")
        if ligne:
            return ligne
    return ""


def langues(env):
    """Codes des langues installees."""
    return [code for code, _nom in env["res.lang"].get_installed()]


def noms(tmpl):
    """Les noms distincts de l'article, toutes langues confondues, hors vides."""
    valeurs = set()
    for code in langues(tmpl.env) + [None]:
        valeur = (tmpl.with_context(lang=code).name or "").strip()
        if valeur:
            valeurs.add(valeur)
    return valeurs


def nom_importe(tmpl):
    """Derniere designation posee par l'import, si la base en garde la trace."""
    if "fma_nom_importe" not in tmpl._fields:
        return ""
    return (tmpl.fma_nom_importe or "").strip()


def nom_libre(tmpl, anciens=()):
    """Vrai si l'import peut encore ecrire le nom : personne ne l'a renomme."""
    admis = {a.strip() for a in anciens if a and a.strip()}
    if nom_importe(tmpl):
        admis.add(nom_importe(tmpl))
    return not (noms(tmpl) - admis)


def ecrire_nom(tmpl, nom):
    """Ecrit le nom dans toutes les langues, et s'en souvient."""
    tmpl = tmpl.sudo()
    for code in [None] + langues(tmpl.env):
        tmpl.with_context(lang=code).write({"name": nom})
    if "fma_nom_importe" in tmpl._fields:
        tmpl.fma_nom_importe = nom


def poser_designation(tmpl, designation, anciens=()):
    """Applique la regle. Renvoie 'ecrit', 'inchange', 'manuel' ou 'vide'."""
    designation = (designation or "").strip()
    if not designation:
        return "vide"
    if noms(tmpl) == {designation}:
        if nom_importe(tmpl) != designation and "fma_nom_importe" in tmpl._fields:
            # Le nom est deja le bon : on note seulement qu'il vient de l'import.
            ecrire_nom(tmpl, designation)
        return "inchange"
    if not nom_libre(tmpl, anciens):
        return "manuel"
    ecrire_nom(tmpl, designation)
    return "ecrit"


def poser_semi_fini(article, parent, suffixe, ancien_parent=""):
    """Nomme l'ensemble debite ou le kit d'apres la menuiserie."""
    modele, _code, ancien = SEMI_FINIS[suffixe]
    parent_tmpl = parent.product_tmpl_id
    base = sorted(noms(parent_tmpl))[:1]
    base = base[0] if base else (parent.default_code or "").strip()
    # Ce que l'import a pu ecrire avant cette regle : « <nom> - debite », avec
    # le nom de la menuiserie de l'epoque -- vide, le plus souvent.
    anciens = [ancien % n for n in noms(parent_tmpl) | {"", ancien_parent or ""}]
    anciens += [a.strip() for a in anciens]
    return poser_designation(article.product_tmpl_id, modele % base, anciens)


def _sans_nom(env):
    """Modeles d'article dont le nom est vide dans toutes les langues."""
    env["product.template"].flush_model(["name"])
    env.cr.execute(
        """SELECT t.id FROM product_template t
            WHERE NOT EXISTS (SELECT 1 FROM jsonb_each_text(t.name) v
                               WHERE btrim(v.value) <> '')
            ORDER BY t.id""")
    ids = [row[0] for row in env.cr.fetchall()]
    return env["product.template"].sudo().with_context(active_test=False).browse(ids)


def _designation_vendue(env, variantes):
    """Designation de la ligne de commande la plus recente, sinon du lot."""
    lignes = env["sale.order.line"].sudo().search(
        [("product_id", "in", variantes.ids)], order="id desc")
    for ligne in lignes:
        trouve = designation_ligne(ligne.name, ligne.product_id.default_code)
        if trouve:
            return trouve, "%s (ligne %s)" % (ligne.order_id.name, ligne.id)
    if "fma.lot.fabrication.line" in env:
        Lot = env["fma.lot.fabrication.line"].sudo()
        if "description" in Lot._fields and "product_id" in Lot._fields:
            for ligne in Lot.search([("product_id", "in", variantes.ids)], order="id desc"):
                trouve = designation_ligne(ligne.description, ligne.product_id.default_code)
                if trouve:
                    return trouve, "lot %s" % ligne.lot_id.display_name
    return "", ""


def _repere(article, reference):
    """Repere de la menuiserie : le champ du connecteur, sinon la fin de la reference."""
    if "x_studio_position" in article._fields and (article.x_studio_position or "").strip():
        return article.x_studio_position.strip()
    return reference.split("_", 1)[-1].strip() or reference


def _reprise(env):
    Product = env["product.product"].sudo().with_context(active_test=False)
    rapport = {
        "articles": [], "sans_designation": [], "semi_finis": [],
        "manuels": [], "codes": [], "nomenclatures_a_voir": [],
    }
    # 1. Les articles sans nom : la designation de leur ligne de commande.
    menuiseries = Product.browse()
    for tmpl in _sans_nom(env):
        variantes = tmpl.product_variant_ids
        reference = (variantes[:1].default_code or "").strip()
        if not reference:
            continue
        menuiseries |= variantes
        designation, source = _designation_vendue(env, variantes)
        if not designation:
            # Rien a reprendre : la ligne ne porte que la reference. Un article
            # sans nom est invisible partout, on lui donne donc son REPERE. Ce
            # nom reste celui de l'import : le prochain depot du fichier le
            # remplacera par la vraie designation.
            repere = _repere(variantes[:1], reference)
            ecrire_nom(tmpl, repere)
            rapport["sans_designation"].append(
                "[%s] « » -> « %s »  (aucune designation sur la ligne)" % (reference, repere))
            continue
        ecrire_nom(tmpl, designation)
        rapport["articles"].append("[%s] « » -> « %s »  (%s)" % (reference, designation, source))
    # 2. Les semi-finis : <ref>-DEB et <ref>-QUI, nommes d'apres la menuiserie.
    couples = []
    for suffixe in SEMI_FINIS:
        for article in Product.search([("default_code", "=like", "%-" + suffixe)], order="id"):
            parent = Product.search(
                [("default_code", "=", article.default_code[:-len(suffixe) - 1])], limit=1)
            if not parent:
                continue
            couples.append((article, parent, suffixe))
            menuiseries |= parent
            avant = " / ".join(sorted(noms(article.product_tmpl_id)))
            # Reprise : la menuiserie etait sans nom quand le semi-fini a ete
            # cree, d'ou l'ancien nom « - debite » tout court.
            resultat = poser_semi_fini(article, parent, suffixe)
            apres = " / ".join(sorted(noms(article.product_tmpl_id)))
            if resultat == "ecrit":
                rapport["semi_finis"].append(
                    "[%s] « %s » -> « %s »" % (article.default_code, avant, apres))
            elif resultat == "manuel":
                rapport["manuels"].append(
                    "[%s] « %s » : nom saisi a la main, laisse" % (article.default_code, avant))
    # 3. Les noms saisis a la main sur une menuiserie : signales, pas touches.
    for parent in menuiseries:
        tmpl = parent.product_tmpl_id
        actuels = noms(tmpl)
        if not actuels or nom_importe(tmpl) in actuels:
            continue
        designation, source = _designation_vendue(env, tmpl.product_variant_ids)
        if designation and actuels == {designation}:
            # Le nom est celui de la ligne : il vient de l'import, qui pourra
            # donc le suivre. Rien n'est renomme, la trace seule est posee.
            poser_designation(tmpl, designation)
        elif not designation and actuels == {_repere(parent, parent.default_code or "")}:
            # Nomme d'apres son repere par une reprise precedente : meme chose.
            poser_designation(tmpl, _repere(parent, parent.default_code or ""))
        elif designation:
            rapport["manuels"].append(
                "[%s] « %s » : la ligne de commande dit « %s » (%s), nom laisse" % (
                    parent.default_code, " / ".join(sorted(actuels)), designation, source))
    # 4. Les references de nomenclature vides.
    if "mrp.bom" in env:
        Bom = env["mrp.bom"].sudo().with_context(active_test=False)
        bases = {}
        for parent in menuiseries:
            boms = Bom.search([("product_tmpl_id", "=", parent.product_tmpl_id.id)], order="id")
            base = (boms.filtered("code")[:1].code or parent.default_code or "").strip()
            bases[parent.id] = base
            for bom in boms.filtered(lambda b: not (b.code or "").strip()):
                bom.code = base
                rapport["codes"].append("nomenclature %s : « %s »" % (bom.id, base))
        for article, parent, suffixe in couples:
            code = SEMI_FINIS[suffixe][1] % (bases.get(parent.id) or parent.default_code)
            for bom in Bom.search([("product_tmpl_id", "=", article.product_tmpl_id.id)]):
                if not (bom.code or "").strip():
                    bom.code = code
                    rapport["codes"].append("nomenclature %s : « %s »" % (bom.id, code))
        # 5. Ce qui reste illisible ou suspect : signale, jamais supprime.
        restants = _sans_nom(env)
        for bom in Bom.search([("product_tmpl_id", "in", restants.ids)], order="id"):
            rapport["nomenclatures_a_voir"].append(
                "nomenclature %s (ref. « %s ») : article id %s toujours sans nom" % (
                    bom.id, bom.code or "", bom.product_tmpl_id.id))
        for bom in Bom.search([("bom_line_ids", "=", False), ("operation_ids", "=", False)], order="id"):
            rapport["nomenclatures_a_voir"].append(
                "nomenclature %s (%s) : ni composant ni operation" % (bom.id, bom.display_name))
        for bom in Bom.search([("product_tmpl_id.active", "=", False), ("active", "=", True)], order="id"):
            rapport["nomenclatures_a_voir"].append(
                "nomenclature %s (%s) : article archive" % (bom.id, bom.display_name))
    return rapport


class _Annulation(Exception):
    """Sert a defaire l'essai a blanc."""


def reprise(env, appliquer=True):
    """Reprise des noms sur l'existant. Rejouable : ce qui est fait le reste.

    ``appliquer=False`` : tout est calcule puis defait, pour lire le rapport
    avant d'ecrire quoi que ce soit.
    """
    rapport = {}
    try:
        with env.cr.savepoint():
            rapport.update(_reprise(env))
            if not appliquer:
                raise _Annulation()
    except _Annulation:
        env.invalidate_all()
    return rapport


TITRES = (
    ("articles", "Articles sans nom, nommes d'apres leur ligne de commande"),
    ("semi_finis", "Ensembles debites et kits quincaillerie renommes"),
    ("codes", "References de nomenclature posees"),
    ("sans_designation", "Articles sans nom et sans designation : nommes d'apres leur repere"),
    ("manuels", "Noms saisis a la main LAISSES tels quels"),
    ("nomenclatures_a_voir", "Nomenclatures a examiner (rien n'est supprime)"),
)


def lignes_rapport(rapport, limite=20):
    """Le rapport, en lignes de texte : un compte et des exemples par rubrique."""
    sortie = []
    for cle, titre in TITRES:
        cas = rapport.get(cle) or []
        sortie.append("%s : %s" % (titre, len(cas)))
        for exemple in cas[:limite] if limite else cas:
            sortie.append("    " + exemple)
        if limite and len(cas) > limite:
            sortie.append("    ... et %s autres" % (len(cas) - limite))
    return sortie
