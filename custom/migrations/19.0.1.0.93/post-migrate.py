# -*- coding: utf-8 -*-
"""Reprise : le numero unique « Siren / Siret » se repartit en SIREN et SIRET.

Jusqu'ici la fiche n'avait qu'un champ, company_registry, ou l'on saisissait
tantot un SIREN (9 chiffres), tantot un SIRET (14 chiffres). Il devient le
SIREN, et le SIRET a son champ, fma_siret.

    14 chiffres  -> SIRET = les 14 chiffres, SIREN = les 9 premiers
     9 chiffres  -> SIREN, inchange (espaces retires)
    autre chose  -> laisse tel quel, liste dans le journal

Les espaces sont ignores pour reconnaitre un numero (« 810 958 298 00012 »).

Ecrit en SQL, volontairement : passer par l'ORM declencherait pour chaque
fiche la synchronisation Iziqo et le suivi des modifications, alors que rien
ne change pour l'exterieur — exports et Iziqo envoient « le SIRET s'il existe,
le SIREN sinon », donc le meme numero qu'avant.

Les fiches des societes internes (res.company) ne sont PAS touchees : le
standard Odoo lit leur company_registry comme un SIRET (pied de page des
documents, facture electronique). Elles sont listees dans le journal.

Rejouable sans effet : apres un premier passage il ne reste plus de numero a
14 chiffres dans company_registry, et un SIRET deja saisi n'est jamais ecrase.
"""
import logging

_logger = logging.getLogger(__name__)

# Nombre de fiches detaillees dans le journal, par categorie.
_MAX_LIGNES = 200

_NETTOYE = r"regexp_replace(p.company_registry, '\s', '', 'g')"


def _liste(lignes):
    texte = "\n".join(
        "    id=%s  %s  SIREN=%r  SIRET=%r" % (pid, nom or "", registre, siret)
        for pid, nom, registre, siret in lignes[:_MAX_LIGNES]
    )
    if len(lignes) > _MAX_LIGNES:
        texte += "\n    … et %s autre(s)" % (len(lignes) - _MAX_LIGNES)
    return texte


def migrate(cr, version):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'res_partner' AND column_name = 'fma_siret'"
    )
    if not cr.fetchone():
        _logger.warning("SIREN/SIRET : colonne fma_siret absente, reprise ignoree.")
        return

    internes = "SELECT partner_id FROM res_company WHERE partner_id IS NOT NULL"

    # 1. Societes internes portant un numero a 14 chiffres : laissees.
    cr.execute(
        f"""
        SELECT p.id, p.name, p.company_registry, p.fma_siret
          FROM res_partner p
         WHERE {_NETTOYE} ~ '^[0-9]{{14}}$'
           AND p.id IN ({internes})
         ORDER BY p.id
        """
    )
    laissees = cr.fetchall()

    # 2. 14 chiffres, mais un SIRET different est deja saisi : on ne tranche pas.
    cr.execute(
        f"""
        SELECT p.id, p.name, p.company_registry, p.fma_siret
          FROM res_partner p
         WHERE {_NETTOYE} ~ '^[0-9]{{14}}$'
           AND p.id NOT IN ({internes})
           AND COALESCE(p.fma_siret, '') <> ''
           AND p.fma_siret <> {_NETTOYE}
         ORDER BY p.id
        """
    )
    conflits = cr.fetchall()

    # 3. 14 chiffres : SIRET = le numero, SIREN = ses 9 premiers chiffres.
    cr.execute(
        f"""
        UPDATE res_partner p
           SET fma_siret = {_NETTOYE},
               company_registry = left({_NETTOYE}, 9)
         WHERE {_NETTOYE} ~ '^[0-9]{{14}}$'
           AND p.id NOT IN ({internes})
           AND (COALESCE(p.fma_siret, '') = '' OR p.fma_siret = {_NETTOYE})
        """
    )
    nb_siret = cr.rowcount

    # 4. 9 chiffres saisis avec des espaces : SIREN, espaces retires.
    cr.execute(
        f"""
        UPDATE res_partner p
           SET company_registry = {_NETTOYE}
         WHERE {_NETTOYE} ~ '^[0-9]{{9}}$'
           AND p.company_registry <> {_NETTOYE}
        """
    )
    nb_espaces = cr.rowcount

    cr.execute(
        "SELECT count(*) FROM res_partner p "
        "WHERE p.company_registry ~ '^[0-9]{9}$'"
    )
    nb_siren = cr.fetchone()[0]

    # 5. Tout le reste : ni 9 ni 14 chiffres. Laisse tel quel.
    cr.execute(
        f"""
        SELECT p.id, p.name, p.company_registry, p.fma_siret
          FROM res_partner p
         WHERE COALESCE(btrim(p.company_registry), '') <> ''
           AND {_NETTOYE} !~ '^([0-9]{{9}}|[0-9]{{14}})$'
         ORDER BY p.id
        """
    )
    atypiques = cr.fetchall()

    _logger.info(
        "SIREN/SIRET : %s fiche(s) a 14 chiffres reparties (SIRET + SIREN), "
        "%s SIREN debarrasse(s) de ses espaces, %s fiche(s) portent un SIREN "
        "a 9 chiffres, %s valeur(s) atypique(s) laissee(s) telle(s) quelle(s), "
        "%s conflit(s) avec un SIRET deja saisi, %s societe(s) interne(s) "
        "non touchee(s).",
        nb_siret, nb_espaces, nb_siren, len(atypiques), len(conflits),
        len(laissees),
    )
    if atypiques:
        _logger.warning(
            "SIREN/SIRET : valeurs ni a 9 ni a 14 chiffres, laissees dans le "
            "SIREN, a reprendre a la main :\n%s", _liste(atypiques))
    if conflits:
        _logger.warning(
            "SIREN/SIRET : numero a 14 chiffres dans le SIREN alors qu'un "
            "SIRET different est deja saisi, fiches non modifiees :\n%s",
            _liste(conflits))
    if laissees:
        _logger.warning(
            "SIREN/SIRET : societes internes dont le numero a 14 chiffres est "
            "conserve (le standard Odoo le lit comme un SIRET) :\n%s",
            _liste(laissees))
