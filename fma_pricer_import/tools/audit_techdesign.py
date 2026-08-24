# -*- coding: utf-8 -*-
"""Audite un export TechDesign avant d'ecrire l'adaptateur pivot.

Repond a deux questions, sur fichiers reels et hors base Odoo :

1. La **phase** groupe-t-elle plusieurs menuiseries, ou recopie-t-elle le
   numero d'item ? C'est elle qui doit porter le lot de fabrication.
2. L'optimisation de mise en barre est-elle **attribuable lot par lot** ?
   Une barre qui porte des coupes de deux phases rend le lot non fabricable
   isolement : le fichier est alors inexploitable en achat comme en production.

Usage :

    python3 audit_techdesign.py ~/Downloads/*.xml

Les trois formats connus sont reconnus a la racine du document :
``JobExport`` (chiffrage), ``JOB`` (scie FOM), ``PMC`` (CNC AluCam).
"""
import sys
import glob
import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict


def _fmt(n, total, libelle):
    pct = (100.0 * n / total) if total else 0.0
    return "%d / %d (%.0f %%) %s" % (n, total, pct, libelle)


def audit_fom(root, nom):
    """Scie FOM : plan de coupe complet, mais sans phase ni fournisseur."""
    barres = root.findall(".//BAR")
    coupes = root.findall(".//CUT")
    print("  format      : liste de debit scie FOM")
    print("  barres      : %d, coupes : %d" % (len(barres), len(coupes)))

    articles = Counter()
    for p in root.findall(".//PDAT"):
        articles[p.findtext("CODE")] = int(float(p.findtext("BQTY") or 0))
    if articles:
        print("  articles    : %d, %d barres au recap HEAD"
              % (len(articles), sum(articles.values())))

    # Le repere de la menuiserie est la 3e etiquette remplie de la coupe.
    def repere(coupe):
        lbls = [(e.text or "").strip() for e in coupe.findall("LBL")]
        remplis = [v for v in lbls if v]
        return remplis[0] if remplis else "?"

    partagees = sum(
        1 for b in barres
        if len({repere(c) for c in b.findall("CUT")}) > 1
    )
    print("  " + _fmt(partagees, len(barres), "barres a cheval sur plusieurs reperes"))

    longueur = chute = 0.0
    for b in barres:
        mlt = float(b.findtext("MLT") or 1)
        longueur += float(b.findtext("LEN") or 0) * mlt
        chute += float(b.findtext("LENR") or 0) * mlt
    if longueur:
        print("  matiere     : %.2f m achetes, %.2f m de chute (%.1f %%)"
              % (longueur / 1000, chute / 1000, 100 * chute / longueur))

    absents = []
    if not any((b.findtext("BRAN") or "").strip() for b in barres):
        absents.append("fournisseur")
    if not any("PHAS" in e.tag.upper() for e in root.iter()):
        absents.append("phase / lot")
    if absents:
        print("  MANQUE      : %s" % ", ".join(absents))
    return {"reperes_partages": partagees, "barres": len(barres)}


def audit_cnc(root, nom):
    """CNC AluCam : porte la phase, mais ne couvre que les barres usinees."""
    generals = root.find("PMCGENERALS")
    if generals is not None:
        print("  format      : programme d'usinage %s" % generals.get("Type"))
        print("  job         : %s — %s"
              % (generals.get("JobId"), generals.get("JobDesc")))
    barres = root.findall(".//BAR")
    coupes = root.findall(".//CUT")
    print("  barres      : %d, coupes : %d, usinages : %d"
          % (len(barres), len(coupes), len(root.findall(".//WORK"))))

    # Question 1 : la phase groupe-t-elle plusieurs menuiseries ?
    par_phase = defaultdict(set)
    for c in coupes:
        par_phase[c.get("Phase")].add(c.get("ItemNo"))
    print("  phases      : %d" % len(par_phase))
    for ph in sorted(par_phase, key=lambda v: (len(v or ""), v or "")):
        items = sorted(par_phase[ph])
        print("     phase %-4s %d menuiserie(s) : %s"
              % (ph, len(items), ", ".join(items[:8])))
    groupe = any(len(v) > 1 for v in par_phase.values())
    print("  => la phase %s plusieurs menuiseries : %s"
          % ("groupe" if groupe else "NE groupe PAS",
             "elle peut porter le lot" if groupe
             else "indiscernable du numero d'item, a confirmer"))

    # Question 2 : l'optimisation est-elle secable par lot ?
    partagees = sum(
        1 for b in barres
        if len({c.get("Phase") for c in b.findall(".//CUT")}) > 1
    )
    print("  " + _fmt(partagees, len(barres), "barres a cheval sur plusieurs phases"))
    if partagees:
        print("  => REFUS : optimisation faite au niveau job, pas au niveau lot.")
        print("     Une barre alimente deux lots, le lot n'est pas fabricable seul.")
    else:
        print("  => OK : chaque barre appartient a une seule phase.")

    longueur = chute = 0.0
    for b in barres:
        n = float(b.get("Count") or 1)
        longueur += float(b.get("Length") or 0) * n
        chute += float(b.get("RestLength") or 0) * n
    if longueur:
        print("  matiere     : %.2f m, %.2f m de chute (%.1f %%) — barres usinees seulement"
              % (longueur / 1000, chute / 1000, 100 * chute / longueur))

    fournisseurs = Counter(b.get("SupplierId") for b in barres)
    teintes = Counter(b.get("Surface") for b in barres)
    print("  fournisseurs: %s" % dict(fournisseurs))
    print("  teintes     : %s" % dict(teintes))
    return {"phase_groupe": groupe, "phases_partagees": partagees,
            "barres": len(barres)}


def audit_chiffrage(root, nom):
    """Job_EXPORT : le seul a porter articles, vitrage et prix."""
    items = root.findall(".//JobItem")
    print("  format      : export chiffrage JobExport")
    print("  menuiseries : %d" % len(items))
    for it in items:
        print("     item %-3s x%-3s %s"
              % (it.get("ItemNumber"), it.get("Quantity"), it.get("Abstract")))

    tags = Counter(e.tag for e in root.iter())
    print("  contenu     : %d profils de debit, %d quincailleries, %d prix"
          % (tags.get("PartLengthArticle", 0),
             tags.get("PartPieceArticle", 0),
             tags.get("Price", 0)))

    # La question qui commande tout : la phase est-elle dans le chiffrage ?
    cles = ("phase", "lot", "batch")
    balises = [t for t in tags if any(k in t.lower() for k in cles)]
    attributs = set()
    for e in root.iter():
        attributs.update(a for a in e.keys() if any(k in a.lower() for k in cles))
    if balises or attributs:
        print("  => LOT PRESENT dans le chiffrage : balises %s, attributs %s"
              % (balises or "-", sorted(attributs) or "-"))
        print("     La voie est ouverte : le lotissement est importable directement.")
    else:
        print("  => AUCUNE notion de lot dans le chiffrage.")
        print("     Le lot devra etre reconstruit depuis le CNC, ou ressaisi.")
    return {"lot_dans_chiffrage": bool(balises or attributs),
            "menuiseries": len(items)}


AUDITS = {"JOB": audit_fom, "PMC": audit_cnc, "JobExport": audit_chiffrage}


def main(chemins):
    resultats = {}
    for chemin in chemins:
        chemin = os.path.expanduser(chemin)
        print("=" * 72)
        print(os.path.basename(chemin))
        print("=" * 72)
        try:
            root = ET.parse(chemin).getroot()
        except ET.ParseError as err:
            print("  ILLISIBLE : %s\n" % err)
            continue
        audit = AUDITS.get(root.tag)
        if audit is None:
            print("  format inconnu (racine <%s>)\n" % root.tag)
            continue
        resultats[root.tag] = audit(root, chemin)
        print()

    print("=" * 72)
    print("VERDICT")
    print("=" * 72)
    chiffrage = resultats.get("JobExport")
    cnc = resultats.get("PMC")
    fom = resultats.get("JOB")

    if chiffrage is None:
        print("  ! Pas d'export chiffrage (Job_EXPORT.xml) : ni devis ni")
        print("    nomenclature ne peuvent etre crees. Les fichiers machine")
        print("    ne portent ni quincaillerie, ni vitrage, ni prix.")
    elif chiffrage["lot_dans_chiffrage"]:
        print("  + Le lot est porte par le chiffrage : import direct possible.")
    else:
        print("  ! Le lot est absent du chiffrage.")

    if cnc is not None:
        if cnc["phases_partagees"]:
            print("  ! Optimisation au niveau job : %d barres a cheval sur"
                  % cnc["phases_partagees"])
            print("    plusieurs phases. A relancer par phase dans le pricer.")
        else:
            print("  + Optimisation secable par lot : aucune barre partagee.")
        if not cnc["phase_groupe"]:
            print("  ? La phase ne groupe qu'une menuiserie : refaire le test")
            print("    avec plusieurs menuiseries par phase pour trancher.")

    if fom is not None and cnc is not None and fom["barres"] != cnc["barres"]:
        print("  ! FOM %d barres contre CNC %d : le CNC ne couvre que les"
              % (fom["barres"], cnc["barres"]))
        print("    barres usinees, ce n'est pas un decompte d'achat.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = sorted(glob.glob(os.path.expanduser("~/Downloads/*.xml")))
    main(args)
