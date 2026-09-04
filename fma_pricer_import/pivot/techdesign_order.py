# -*- coding: utf-8 -*-
"""Adaptateur TechDesign : export de commande fournisseur -> format pivot.

Quatrieme format TechDesign, et le seul qui ne decrive pas de menuiseries. Les
exports chiffrage (``JobExport``), scie (``JOB``) et CNC (``PMC``) disent ce
qu'il faut FABRIQUER ; celui-ci dit ce qui a ete COMMANDE a un fournisseur.

Il ne peut donc pas creer de devis : il ne porte ni position, ni coupe, ni
menuiserie — verifie sur fichier reel, aucune ligne n'a de ``orderRefNumber``.
Il se rattache a une affaire et a ses lots, jamais plus finement.

Ce qu'il apporte est precisement ce qui manque au chiffrage : le besoin
d'achat REEL, conditionnement compris. Le chiffrage dit qu'il faut 40 pieces ;
la commande dit qu'on en achete 50, parce qu'elles se vendent par sachet.

Racine du document : ``<root>``, reconnue au noeud ``m_OrderBlob``. Les
quantites de barres sont en nombre de barres, ``m_dPackUnit`` donnant la
longueur d'une barre en millimetres — cette unite differe donc de celle des
articles piece, ou ``m_dPackUnit`` est un nombre de pieces par conditionnement.
"""
import os
import xml.etree.ElementTree as ET

from .schema import OrderLine, Purchase, Quotation

#: Les trois listes d'articles d'une commande, et le genre de ligne produit.
LISTES = (
    ("m_OrderPieceArticleList", "piece"),
    ("m_OrderLengthArticleList", "bar"),
    ("m_OrderFixedGlazingList", "glass"),
)


def est_commande(root):
    """Vrai si le document est un export de commande, pas un chiffrage."""
    return root.find("object/m_OrderBlob") is not None


def parse(path, source=None):
    """Lit un export de commande TechDesign et renvoie un ``Quotation``."""
    root = ET.parse(path).getroot()
    if not est_commande(root):
        raise ValueError(
            "Ce fichier n'est pas un export de commande TechDesign : "
            "aucun noeud m_OrderBlob sous <%s>." % root.tag
        )
    return _parse(root, source or os.path.basename(path))


def _valeur(noeud, chemin, defaut=0.0):
    """Lit un attribut ``v`` numerique, absent des exports anciens."""
    trouve = noeud.find(chemin) if noeud is not None else None
    if trouve is None:
        return defaut
    brut = trouve.get("v")
    if brut in (None, ""):
        return defaut
    try:
        return float(brut)
    except ValueError:
        return defaut


def _texte(noeud, chemin, defaut=""):
    valeur = noeud.findtext(chemin) if noeud is not None else None
    return (valeur or defaut).strip()


def _ligne(item, genre, fournisseur_commande, devise):
    """Traduit un article de la commande en ligne d'achat du pivot."""
    return OrderLine(
        kind=genre,
        code=_texte(item, "m_ArticleId/code"),
        art_num=_texte(item, "m_sArtNum"),
        description=_texte(item, "m_sDescription"),
        # La teinte est le code de commande de la finition, pas son libelle :
        # c'est lui qui distingue deux articles Odoo de meme reference.
        color=_texte(item, "m_SfOrderInfo/m_sSfOrderCode"),
        # Le fournisseur de la ligne prime sur celui de la commande : une
        # commande TECHNAL porte des articles dont certains viennent d'ailleurs.
        supplier=_texte(item, "m_SupplierId/code") or fournisseur_commande,
        qty_needed=_valeur(item, "m_dQuantCalc"),
        qty_ordered=_valeur(item, "m_dQuantPackaged"),
        pack_qty=_valeur(item, "m_dPackUnit"),
        pack_count=_valeur(item, "m_iQuantPackUnit"),
        unit_price=_valeur(item, "m_PricePerUnit/m_Price"),
        total_price=_valeur(item, "m_PriceTotal/m_Price"),
        currency=_texte(item, "m_PriceTotal/m_CurrencyId") or devise,
    )


def _parse(root, source):
    blob = root.find("object/m_OrderBlob")
    quo = Quotation(pricer="techdesign", source=source)

    fournisseur = _texte(blob, "m_SupplierId/code")
    devise = _texte(blob, "m_VarAdditionalPriceForWeight/m_CurrencyId")

    origine = blob.find("m_OriginEntityList/item")
    affaire = _texte(origine, "m_EntityDbId/code")
    lots = [
        (item.text or "").strip()
        for item in (origine.findall("m_EntitySubNrList/item") if origine is not None else [])
        if (item.text or "").strip()
    ]

    achat = Purchase(
        supplier=fournisseur,
        ref=_texte(blob, "m_sCustomNum") or root.get("dbid") or "",
        description=_texte(blob, "m_sDescription"),
        affaire=affaire,
        lots=lots,
        currency=devise,
    )
    for liste, genre in LISTES:
        for item in blob.findall("%s/item" % liste):
            achat.lines.append(_ligne(item, genre, fournisseur, devise))

    quo.purchases.append(achat)
    quo.project = {
        "name": achat.description,
        "offer_no": affaire,
        "order_no": achat.ref,
    }

    if not affaire:
        quo.warnings.append(
            "La commande %s ne porte aucune affaire d'origine : elle n'est "
            "rattachable a aucun devis." % (achat.ref or source)
        )
    if not achat.lines:
        quo.warnings.append("La commande %s ne porte aucun article." % achat.ref)
    # Aucune menuiserie : le dire ici plutot que de laisser l'appelant croire
    # a un chiffrage vide.
    quo.warnings.append(
        "Export de commande : ni menuiserie, ni position, ni coupe. Il "
        "complete un lot deja importe, il ne le cree pas."
    )
    return quo
