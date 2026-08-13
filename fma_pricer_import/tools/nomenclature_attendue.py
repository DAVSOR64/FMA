# -*- coding: utf-8 -*-
"""Nomenclature attendue, produite par le code de lecture du module lui-meme.

A lancer depuis la racine du depot :
    python3 <ce fichier> "~/Downloads/lot 2.sqlite3"

Ce que l'on obtient est exactement ce que l'import ecrira dans Odoo : meme
adaptateur, memes regles de couleur, memes temps. Ce qui differe a l'ecran
vient donc d'Odoo — article introuvable, poste de charge absent — et non de
la lecture du fichier.
"""
import importlib.util
import os
import sys

BASE = "fma_pricer_import/pivot"


def charger_pivot():
    spec = importlib.util.spec_from_file_location("schema", BASE + "/schema.py")
    schema = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(schema)
    sys.modules["schema"] = schema
    src = open(BASE + "/logikal.py", encoding="utf-8").read().replace(
        "from .schema import", "from schema import")
    mod = type(sys)("logikal")
    exec(compile(src, "logikal.py", "exec"), mod.__dict__)
    return mod


def main(chemin):
    quo = charger_pivot().parse(os.path.expanduser(chemin))
    print("=" * 78)
    print("NOMENCLATURE ATTENDUE — %s" % os.path.basename(chemin))
    print("=" * 78)
    print("Devis (OfferNo) : %s" % quo.project.get("offer_no"))
    print("Site            : %s" % (quo.site or "(absent)"))
    print("Barres par lot  : %s" % ("oui" if quo.bars_per_lot else "NON — inexploitable"))

    for lot in quo.lots:
        print("\n" + "-" * 78)
        print("LOT %s — %d menuiserie(s), %d barre(s)"
              % (lot.ref, len(lot.menuiseries), len(lot.bars)))
        print("-" * 78)
        for men in lot.menuiseries:
            print("\n  %s « %s »   x %g exemplaire(s)   %g x %g mm"
                  % (men.position or men.ref, men.description, men.qty,
                     men.width_mm, men.height_mm))

            print("    COMPOSANTS (pour UN exemplaire)")
            print("      1 x  <sous-ensemble debite>   (ajoute par l'import)")
            # Le moteur fusionne les lignes d'un meme article : une reference
            # en une teinte donnee est UN article Odoo, donc UNE ligne de
            # nomenclature. On fusionne pareil, sans quoi la comparaison a
            # l'ecran serait fausse.
            fusion = {}
            for c in men.components:
                cle = (c.kind, c.code, c.color)
                cumul = fusion.setdefault(cle, [0.0, c.uom, c.description])
                cumul[0] += c.qty
            for (kind, code, couleur), (qte, uom, desc) in sorted(fusion.items()):
                teinte = (" [%s]" % couleur) if couleur else ""
                marque = "V" if kind == "glass" else " "
                print("      %s %-10.4f %-4s %-22s %s%s"
                      % (marque, qte, uom or "", code, (desc or "")[:26], teinte))

            print("    GAMME (minutes pour UN exemplaire)")
            for o in men.operations:
                cible = "nomenclature du debite" if o.name == "Debit" else "nomenclature menuiserie"
                print("      seq %-3s %-12s %8.2f   -> %s"
                      % (o.sequence, o.name, o.minutes, cible))

            print("    DEBIT : %d coupe(s), %.0f mm par exemplaire"
                  % (len(men.debit), men.debit_mm))

        if lot.bars:
            print("\n  BARRES ACHETEES PAR LE LOT")
            par_ref = {}
            for b in lot.bars:
                cle = (b.code, getattr(b, "color", ""))
                par_ref[cle] = par_ref.get(cle, 0) + 1
            for (code, couleur), nb in sorted(par_ref.items()):
                print("      %-24s %-14s %d barre(s)" % (code, couleur or "", nb))

    print("\n" + "=" * 78)
    lignes = quo.sale_lines() if hasattr(quo, "sale_lines") else []
    if lignes:
        print("LIGNES DE DEVIS ATTENDUES")
        for l in lignes:
            print("  %-14s %-34s qte %g   %s"
                  % (l.ref, (l.description or "")[:34], l.qty, l.qty_by_lot))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "~/Downloads/lot 2.sqlite3")
