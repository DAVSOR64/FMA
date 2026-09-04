# -*- coding: utf-8 -*-
"""Adaptateur TechDesign : export de chiffrage ``JobExport`` -> format pivot.

C'est l'export qui porte tout : menuiseries, debit, quincaillerie, vitrage,
prix et lots. Les trois autres formats TechDesign ne le remplacent pas — la
scie et le CNC ne connaissent ni prix ni quincaillerie, et la commande
fournisseur ne connait pas les menuiseries.

Constate sur export reel, et decisif pour l'import :

* le **lot** est natif : ``JobPhase`` porte ``PhaseNumber`` et un libelle
  (« LOT 1 »). Rien a ressaisir ;
* le **repere** suit la meme convention que LOGIKAL : une menuiserie repetee
  dans cinq lots s'appelle « A », « A_2 », « A_3 »... C'est donc
  ``logikal.base_position`` qui la resout, et cinq positions de lots
  differents redeviennent une seule ligne de devis ;
* les **valeurs numeriques** sont dans des attributs, jamais dans le texte :
  ``<Length Quantity="2090.33" Unit="mm"/>``, ``<Price Price="24.20"/>``. Un
  parseur qui lirait ``.text`` ne trouverait que du vide ;
* la **teinte** des lignes de nomenclature est un libelle (« Prix 20SELCT2 »,
  « *XBLACK ») alors que le catalogue et la commande fournisseur portent le
  code d'achat (« 20SELCT2 », « XBLACK »). Sans nettoyage, aucun article ne
  serait retrouve dans Odoo.

Limite du format : ``Profiles`` et ``Fittings`` sont **globaux au chiffrage**,
pas par phase. Les barres ne sont donc attribuables a un lot que si l'export
n'en contient qu'un — c'est ce que dit ``bars_per_lot``.
"""
import os
import re
import xml.etree.ElementTree as ET

from .logikal import base_position
from .schema import Bar, Component, Cut, Lot, Menuiserie, Operation, Quotation

#: Prefixes ajoutes par TechDesign au code de finition sur les lignes de
#: nomenclature. « * » marque une teinte imposee, « Prix » une teinte tarifaire.
TEINTE_PREFIXES = re.compile(r"^(?:\*|Prix\s+)+")

#: Teintes qui signifient « pas de finition ». Alignees sur logikal.color_of,
#: qui rend une chaine vide : sans cela le meme profile brut serait cherche
#: sous deux teintes selon le pricer.
SANS_TEINTE = {"SANS", "ZNCO", ""}


def teinte(brut):
    """Code d'achat de la finition, tel que le catalogue le porte."""
    valeur = TEINTE_PREFIXES.sub("", (brut or "").strip()).strip()
    return "" if valeur.upper() in SANS_TEINTE else valeur


def reference(identifiant):
    """Reference nue de l'article.

    ``Id`` vaut « TECHNAL,226521 » sur un profile et « TECHNAL,720028 » sur
    une quincaillerie : le fournisseur precede la reference. On ne garde que
    la reference, seule comparable a ``x_studio_ref_int_logikal``.
    """
    identifiant = (identifiant or "").strip()
    if "," in identifiant:
        return identifiant.split(",", 1)[1].strip()
    return identifiant


def _nombre(noeud, tag, attribut="Quantity"):
    """Valeur numerique d'un enfant, portee par un attribut et non par le texte."""
    trouve = noeud.find(tag) if noeud is not None else None
    if trouve is None:
        return 0.0
    try:
        return float(trouve.get(attribut) or 0)
    except ValueError:
        return 0.0


def _attr_nombre(noeud, attribut):
    try:
        return float((noeud.get(attribut) or "").strip() or 0)
    except ValueError:
        return 0.0


def parse(path, source=None):
    """Lit un export de chiffrage TechDesign et renvoie un ``Quotation``."""
    root = ET.parse(path).getroot()
    if root.tag != "JobExport":
        raise ValueError(
            "Ce fichier n'est pas un export de chiffrage TechDesign : "
            "racine <%s> au lieu de <JobExport>." % root.tag
        )
    return _parse(root, source or os.path.basename(path))


def _fournisseurs(root):
    """Fournisseur par (reference, teinte), depuis les catalogues du chiffrage.

    Les lignes de nomenclature ne portent pas le fournisseur : il n'existe que
    dans ``Profiles``, ``PieceProfiles`` et ``Fittings``, qui recapitulent
    l'affaire entiere.
    """
    table = {}
    for chemin in ("./Job/Profiles/Profile",
                   "./Job/PieceProfiles/PieceProfile",
                   "./Job/Fittings/Fitting"):
        for article in root.findall(chemin):
            fournisseur = article.find("Supplier")
            if fournisseur is None:
                continue
            nom = (fournisseur.get("SupplierDescription")
                   or fournisseur.get("SupplierCode") or "").strip()
            if nom:
                table[(article.get("Code") or "",
                       teinte(article.get("SurfaceOrderCode")))] = nom
    return table


def _composants(item, fournisseurs):
    """Quincaillerie et vitrage d'une menuiserie, pour un exemplaire."""
    composants = []
    for part in item.findall("PartsList/PartArticle/PartPieceArticle"):
        code = reference(part.get("Id"))
        couleur = teinte(part.get("SurfaceFinish"))
        composants.append(Component(
            kind="article",
            code=code,
            description=(part.get("Description") or "").strip(),
            qty=_attr_nombre(part, "Quantity"),
            color=couleur,
            supplier=fournisseurs.get((code, couleur), ""),
        ))
    for pane in item.findall("PartsList/PartArticle/PartPane"):
        composants.append(Component(
            kind="glass",
            # Le vitrage n'a pas de reference article : sa designation le
            # nomme, et c'est elle que porte l'article Odoo cree a l'import.
            code=(pane.get("Description") or "").strip(),
            description=(pane.get("Composition") or "").strip(),
            qty=_attr_nombre(pane, "Quantity"),
            width_mm=_nombre(pane, "Width"),
            height_mm=_nombre(pane, "Height"),
        ))
    return composants


def _debit(item, fournisseurs):
    """Coupes de profile d'une menuiserie, pour un exemplaire."""
    coupes = []
    for part in item.findall("PartsList/PartArticle/PartLengthArticle"):
        code = reference(part.get("Id"))
        couleur = teinte(part.get("SurfaceFinish"))
        coupes.append(Cut(
            code=code,
            description=(part.get("Description") or "").strip(),
            color=couleur,
            supplier=fournisseurs.get((code, couleur), ""),
            length_mm=_nombre(part, "Length"),
            qty=_attr_nombre(part, "Quantity"),
        ))
    return coupes


def _operations(item):
    """Temps de main d'oeuvre declares sur la menuiserie.

    Seules les lignes en heures sont retenues : ``AdditionalCostsAndHours``
    melange des temps et des forfaits en euros.

    Les libelles sont ceux de TechDesign (« Heures Fabrication », « Heures
    Pose »...), plus grossiers que ceux de LOGIKAL. Le rattachement au poste
    de charge se declare sur le poste, champ « Operation pricer ».
    """
    operations = []
    for rang, ligne in enumerate(
            item.findall("AdditionalCostsAndHours/AdditionalCostAndHour")):
        if (ligne.get("Unit") or "").strip().lower() != "h":
            continue
        heures = _attr_nombre(ligne, "Value")
        if not heures:
            continue
        operations.append(Operation(
            name=(ligne.get("Description") or "").strip(),
            minutes=heures * 60.0,
            sequence=(rang + 1) * 10,
        ))
    return operations


def _barres(root, fournisseurs):
    """Barres achetees, telles que le chiffrage les a optimisees."""
    barres = []
    for chemin in ("./Job/Profiles/Profile", "./Job/PieceProfiles/PieceProfile"):
        for article in root.findall(chemin):
            longueur = _nombre(article, "Length")
            quantite = _attr_nombre(article, "Quantity")
            if not longueur or not quantite:
                continue
            code = article.get("Code") or ""
            couleur = teinte(article.get("SurfaceOrderCode"))
            # RestLength est la chute TOTALE du poste, tous exemplaires
            # confondus : le consomme s'en deduit, il n'est pas donne.
            chute = _nombre(article, "RestLength")
            barres.append(Bar(
                code=code,
                description=(article.get("Description") or "").strip(),
                supplier=fournisseurs.get((code, couleur), ""),
                color=couleur,
                length_mm=longueur,
                qty=quantite,
                used_mm=max(longueur - (chute / quantite if quantite else 0.0), 0.0),
            ))
    return barres


def _parse(root, source):
    quo = Quotation(pricer="techdesign", source=source)
    fournisseurs = _fournisseurs(root)

    job = root.find("Job")
    general = job.find("General") if job is not None else None
    quo.project = {
        "name": (job.get("Description") or job.get("Name") or "").strip() if job is not None else "",
        "offer_no": (job.get("Number") or job.get("JobNumber") or "").strip() if job is not None else "",
        "order_no": (general.findtext("CreationDate") or "").strip() if general is not None else "",
    }

    phases = root.findall(".//JobItems/JobPhase")
    for phase in phases:
        libelle = (phase.get("Description") or "").strip()
        numero = (phase.get("PhaseNumber") or "").strip()
        lot = Lot(ref=libelle or ("LOT %s" % numero), guid=numero)
        for item in phase.findall("JobItem"):
            repere = (item.get("JobNumber") or item.get("ItemNumber") or "").strip()
            lot.menuiseries.append(Menuiserie(
                ref=repere,
                # Meme convention que LOGIKAL : « A_3 » dans le lot 3 est la
                # position « A ». Cinq lots d'une meme menuiserie ne font donc
                # qu'une ligne de devis.
                position=base_position(repere, lot.ref),
                description=(item.get("Abstract") or "").strip(),
                qty=_attr_nombre(item, "Quantity") or 1.0,
                width_mm=_nombre(item, "Width"),
                height_mm=_nombre(item, "Height"),
                price=_nombre(item, "SpreadingEnforcement/TotalUnitFinalPrice", "Price"),
                components=_composants(item, fournisseurs),
                debit=_debit(item, fournisseurs),
                operations=_operations(item),
            ))
        quo.lots.append(lot)

    # Les catalogues d'articles recapitulent l'affaire entiere, sans distinguer
    # les phases : une barre ne peut donc etre rattachee a un lot que s'il n'y
    # en a qu'un. Sinon on ne rattache rien plutot que d'imputer au hasard.
    #
    # bars_per_lot reste VRAI pour autant. Ce drapeau dit « une meme barre
    # alimente plusieurs lots, donc aucun lot n'est fabricable seul », et le
    # moteur refuse alors l'import. Ce n'est pas notre cas : le debit et la
    # nomenclature de chaque menuiserie sont bien portes par leur lot, seul le
    # besoin d'ACHAT manque. Bloquer l'import pour cela priverait du devis, des
    # lots et des nomenclatures a cause d'une mesure accessoire.
    barres = _barres(root, fournisseurs)
    if len(phases) <= 1 and quo.lots:
        quo.lots[0].bars = barres
    elif barres:
        quo.warnings.append(
            "Le chiffrage porte %d lot(s) mais ses barres sont recapitulees "
            "pour l'affaire entiere : le besoin d'achat n'est pas ventilable "
            "par lot et n'a donc pas ete repris. La fabrication, elle, n'est "
            "pas affectee. Exporter lot par lot pour disposer aussi des "
            "barres." % len(phases)
        )

    if not phases:
        quo.warnings.append("Aucune phase dans le chiffrage : aucun lot a creer.")
    noms = sorted({o.name for lot in quo.lots
                   for m in lot.menuiseries for o in m.operations})
    if noms:
        quo.warnings.append(
            "Temps declares sous : %s. Rattacher chacun a un poste de charge "
            "(champ « Operation pricer » du poste) — TechDesign nomme ses "
            "temps autrement que LOGIKAL." % ", ".join(noms)
        )
    return quo
