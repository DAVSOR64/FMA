# -*- coding: utf-8 -*-
"""La reference LOGIKAL d'un article, telle que ce module la stocke.

Le fichier du pricer ne porte pas la reference que l'on retrouve ensuite dans
``x_studio_ref_int_logikal`` : elle est construite, et la construction depend
du FOURNISSEUR. Technal prefixe d'un T, Wicona d'un W sur sept chiffres, Sapa
d'un S ; les autres gardent le code tel quel. Un code deja prefixe d'un X est
laisse intact — c'est une reference interne au chiffreur.

La regle vit ici, et non dans la boucle d'import, parce qu'elle a DEUX
lecteurs : le connecteur qui ecrit les articles, et l'import pricer qui doit
les retrouver. Tant qu'elle n'existait qu'au premier, le second cherchait des
references qui n'ont jamais ete ecrites — « article 0525371.-- inexistant »
pour un article qui etait bien la, sous « 0525371 ».

Elle part d'``ArticleCode_BaseNumber`` et non d'``ArticleCode_Number`` : le
second porte le suffixe de teinte (« 0525371.-- »), le premier non.
"""

#: Prefixe de reference LOGIKAL, par fournisseur.
PREFIXE_PAR_FOURNISSEUR = {
    "TECHNAL": "T",
    "WICONA": "W",
    "SAPA": "S",
}

#: Wicona complete ses references a sept chiffres.
LONGUEUR_WICONA = 7


def ref_logikal(fournisseur, base_code):
    """Reference LOGIKAL pour ``base_code`` chez ``fournisseur``.

    ``base_code`` est ``ArticleCode_BaseNumber``, sans suffixe de teinte.
    Renvoie la chaine vide pour un code vide, jamais None.
    """
    base = (base_code or "").strip()
    if not base:
        return ""
    # Un code deja en X est une reference du chiffreur : on n'y touche pas.
    if base.startswith("X"):
        return base

    prefixe = _prefixe(fournisseur)
    if not prefixe:
        return base
    if prefixe == "W" and len(base) < LONGUEUR_WICONA:
        return prefixe + base.zfill(LONGUEUR_WICONA)
    return prefixe + base


def _prefixe(fournisseur):
    """Le prefixe du fournisseur, reconnu meme sur un libelle approchant.

    Le connecteur lit ``ArticleCode_Supplier`` — « WICONA » tout court. Le
    pivot, lui, prend le libelle de la table Suppliers, qui peut valoir
    « WICONA FRANCE » ou porter une raison sociale. Comparer les deux a
    l'identique faisait echouer la regle pour Wicona alors qu'elle passait
    pour Technal, ou les deux libelles coincident.

    On reconnait donc le fournisseur par INCLUSION, apres l'egalite. Les trois
    noms concernes sont assez distinctifs pour qu'une inclusion ne se trompe
    pas de maison.
    """
    frs = (fournisseur or "").strip().upper()
    if not frs:
        return ""
    prefixe = PREFIXE_PAR_FOURNISSEUR.get(frs)
    if prefixe:
        return prefixe
    for nom, prefixe in PREFIXE_PAR_FOURNISSEUR.items():
        if nom in frs:
            return prefixe
    return ""


# ----------------------------------------------------------------------
# Destination du vitrage
# ----------------------------------------------------------------------
#
# LOGIKAL porte l'information dans Glass.Info2, en TEXTE LIBRE. Releve sur
# dix-neuf affaires reelles : « SUR CHARIOT », « Sur chariot », « Sur
# chariot chantier », et du vide. La consigne donnee aux deviseurs est
# desormais deux mots, CHARIOT ou PALETTE, mais la base porte l'ancien et
# un deviseur se trompera : la lecture reste tolerante, et signale.
#
# Chariot = le vitrage reste a l'atelier. Palette = il part chez le client,
# en transitant par FMA. La distinction decide de la commande d'achat, donc
# du quai de reception : elle ne peut pas rester implicite.

DESTINATION_CHARIOT = "chariot"
DESTINATION_PALETTE = "palette"

#: Destinations possibles, pour les champs Selection.
DESTINATIONS_VITRAGE = [
    (DESTINATION_CHARIOT, "Chariot — atelier"),
    (DESTINATION_PALETTE, "Palette — chantier"),
]

_ACCENTS = str.maketrans("ÀÁÂÃÄÅÈÉÊËÌÍÎÏÒÓÔÕÖÙÚÛÜÇ", "AAAAAAEEEEIIIIOOOOOUUUUC")


def destination_vitrage(info2):
    """(destination, anomalie) pour un Glass.Info2 de LOGIKAL.

    ``anomalie`` vaut la valeur brute quand elle n'est pas conforme a la
    consigne — vide, ancienne formulation, faute de frappe. Elle n'est pas
    une erreur bloquante : on retombe sur CHARIOT, et l'appelant signale.

    LE REPLI EST CHARIOT, ET C'EST VOLONTAIRE. Un vitrage de chantier traite
    comme un chariot arrive a l'atelier, ou il passe de toute facon : on le
    recharge. L'inverse — une palette expediee au chantier alors qu'elle
    devait rester — ne se rattrape qu'au dechargement.
    """
    texte = (info2 or "").strip().upper().translate(_ACCENTS)
    if not texte:
        return DESTINATION_CHARIOT, "(vide)"
    # LE CHEVALET BOIS EST UNE PALETTE. C'est un cadre de transport, pas un
    # support d'atelier : le vitrage qu'il porte part chez le client. Releve
    # sur KIT5 Lot 2, ou LOGIKAL ecrit « SUR CHEVALLET BOIS » — avec deux L,
    # d'ou les deux orthographes acceptees.
    if any(mot in texte for mot in ("PALETTE", "CHEVALET", "CHEVALLET")):
        return DESTINATION_PALETTE, ""
    if texte == "CHARIOT" or texte == "SUR CHARIOT":
        return DESTINATION_CHARIOT, ""
    # « SUR CHARIOT CHANTIER » et consorts : l'intention est lisible, la
    # saisie ne l'est pas. On ne devine pas a la place du deviseur.
    return DESTINATION_CHARIOT, info2
