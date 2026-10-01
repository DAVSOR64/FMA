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
