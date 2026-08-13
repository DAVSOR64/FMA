# -*- coding: utf-8 -*-
"""Structure du format pivot, commune a tous les pricers.

Le pivot est volontairement du Python nu (dataclasses) : il doit pouvoir etre
construit et controle sans base Odoo, dans un simple script.

Unites normalisees :

* longueurs en **millimetres** (les pricers melangent m et mm) ;
* quantites de composants **par exemplaire de menuiserie**, jamais cumulees ;
* quantites de barres **par lot**, cumulees, telles que le pricer les a
  optimisees.
"""
from dataclasses import dataclass, field


@dataclass
class Component:
    """Article ou vitrage consomme par une menuiserie, pour un exemplaire."""

    kind: str  # "article" | "glass"
    code: str
    description: str = ""
    qty: float = 0.0
    uom: str = ""
    supplier: str = ""
    #: Teinte, telle que le connecteur la porte dans ``x_studio_color_logikal``.
    #: Une meme reference en deux teintes = deux articles Odoo distincts.
    color: str = ""
    price: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0


@dataclass
class Cut:
    """Coupe de profile necessaire a un exemplaire de menuiserie."""

    code: str
    description: str = ""
    supplier: str = ""
    color: str = ""
    length_mm: float = 0.0
    qty: float = 0.0

    @property
    def total_mm(self):
        return self.length_mm * self.qty


@dataclass
class Operation:
    """Temps de main d'oeuvre d'une menuiserie, pour un exemplaire."""

    name: str
    minutes: float = 0.0
    sequence: int = 10


@dataclass
class Menuiserie:
    """Une ligne d'etude du pricer = une ligne de devis Odoo."""

    ref: str
    description: str = ""
    #: Position independante du lot : LOGIKAL suffixe « A » en « A_1 » dans le
    #: lot 1, « A_2 » dans le lot 2. C'est la position de base qui identifie
    #: l'article fabrique, d'un export a l'autre.
    position: str = ""
    qty: float = 1.0  # nombre d'exemplaires identiques
    width_mm: float = 0.0
    height_mm: float = 0.0
    price: float = 0.0
    components: list = field(default_factory=list)  # [Component]
    debit: list = field(default_factory=list)  # [Cut], pour UN exemplaire
    operations: list = field(default_factory=list)  # [Operation], pour UN exemplaire

    @property
    def debit_mm(self):
        """Longueur de profile consommee par un exemplaire."""
        return sum(c.total_mm for c in self.debit)

    def signature(self):
        """Empreinte de ce qui est *fabrique*, independamment du lot.

        Deux positions de lots differents qui produisent la meme empreinte sont
        le meme produit : meme article fabrique, meme nomenclature, donc **une
        seule ligne de devis** — le decoupage en lots n'est qu'un quantitatif
        de production.

        L'empreinte ignore volontairement le repere du pricer (``A_1``,
        ``A_2``...), qui change d'un lot a l'autre pour une menuiserie
        identique, et ne retient que la definition technique : designation,
        dimensions, composants et debit.
        """
        if not self.is_manufactured:
            # Position de texte, remise, transport, eco-contribution : rien
            # n'est fabrique, donc rien a mutualiser. Le repere seul fait foi,
            # sans quoi deux lignes de frais differentes fusionneraient.
            return ("!", self.ref.strip())
        comps = sorted(
            (c.kind, c.code, c.color, round(c.qty, 4),
             round(c.width_mm), round(c.height_mm))
            for c in self.components
        )
        cuts = sorted(
            (c.code, c.color, round(c.length_mm, 1), round(c.qty, 4))
            for c in self.debit
        )
        return (
            self.description.strip(),
            round(self.width_mm),
            round(self.height_mm),
            tuple(comps),
            tuple(cuts),
        )

    @property
    def is_manufactured(self):
        """Vrai si la position produit quelque chose (nomenclature non vide)."""
        return bool(self.components or self.debit)


@dataclass
class Bar:
    """Barre physique achetee, telle qu'optimisee par le pricer pour ce lot."""

    code: str
    description: str = ""
    supplier: str = ""
    color: str = ""
    length_mm: float = 0.0
    qty: float = 1.0
    used_mm: float = 0.0

    @property
    def loss_mm(self):
        return (self.length_mm - self.used_mm) * self.qty


@dataclass
class Lot:
    """Lot de fabrication : le perimetre insecable de l'optimisation de debit."""

    ref: str
    guid: str = ""
    menuiseries: list = field(default_factory=list)  # [Menuiserie]
    bars: list = field(default_factory=list)  # [Bar]

    @property
    def debit_mm(self):
        """Besoin reel du lot, tous exemplaires confondus."""
        return sum(m.debit_mm * m.qty for m in self.menuiseries)

    @property
    def bars_mm(self):
        return sum(b.length_mm * b.qty for b in self.bars)

    @property
    def bar_count(self):
        return sum(b.qty for b in self.bars)


@dataclass
class Quotation:
    """Resultat d'un import : un chiffrage, un ou plusieurs lots."""

    pricer: str
    source: str = ""
    project: dict = field(default_factory=dict)
    lots: list = field(default_factory=list)  # [Lot]
    warnings: list = field(default_factory=list)
    #: Site qui a chiffre — « FMA » ou « F2M ». Il departage les postes de
    #: charge homonymes des deux ateliers (« Debit FMA » / « Debit F2M »).
    site: str = ""
    #: Vrai si l'optimisation de debit est attribuable lot par lot. Faux quand
    #: une barre porte des coupes de plusieurs lots : les barres du fichier ne
    #: sont alors exploitables ni en achat ni en production.
    bars_per_lot: bool = True

    @property
    def debit_mm(self):
        return sum(lot.debit_mm for lot in self.lots)

    @property
    def bar_count(self):
        return sum(lot.bar_count for lot in self.lots)

    def merge(self, other):
        """Ajoute un second chiffrage a celui-ci, lot par lot.

        C'est le scenario nominal : un export par lot, deposes l'un apres
        l'autre sur le meme devis. Un lot deja present est **remplace** — on
        reimporte un lot corrige sans toucher aux autres.
        """
        by_ref = {lot.ref: i for i, lot in enumerate(self.lots)}
        for lot in other.lots:
            if lot.ref in by_ref:
                self.lots[by_ref[lot.ref]] = lot
            else:
                by_ref[lot.ref] = len(self.lots)
                self.lots.append(lot)
        self.warnings.extend(other.warnings)
        self.bars_per_lot = self.bars_per_lot and other.bars_per_lot
        return self

    def sale_lines(self):
        """Regroupe les menuiseries en lignes de devis.

        Une ligne commerciale par produit fabrique, quel que soit le nombre de
        lots qui la fabriquent : c'est la vue client. Chaque ligne conserve sa
        repartition par lot, qui alimente ``fma.lot.fabrication.line`` et donc
        la production.

        Renvoie une liste de :class:`SaleLine`, dans l'ordre d'apparition.
        """
        lines = {}
        for lot in self.lots:
            for men in lot.menuiseries:
                key = men.signature()
                line = lines.get(key)
                if line is None:
                    line = lines[key] = SaleLine(
                        ref=men.ref, description=men.description, menuiserie=men
                    )
                elif men.ref not in line.refs:
                    line.refs.append(men.ref)
                line.qty += men.qty
                line.qty_by_lot[lot.ref] = line.qty_by_lot.get(lot.ref, 0.0) + men.qty
        return list(lines.values())


@dataclass
class SaleLine:
    """Une ligne de devis : un produit fabrique, reparti sur un ou plusieurs lots."""

    ref: str
    description: str = ""
    qty: float = 0.0
    #: Quantite a fabriquer par lot : ``{"LOT 1": 10.0, "LOT 2": 10.0, ...}``
    qty_by_lot: dict = field(default_factory=dict)
    #: Reperes du pricer regroupes sous cette ligne (``A_1``, ``A_2``...).
    refs: list = field(default_factory=list)
    #: Une des menuiseries du groupe : elles sont techniquement identiques,
    #: c'est elle qui porte la nomenclature et le debit unitaire.
    menuiserie: object = None

    def __post_init__(self):
        if not self.refs:
            self.refs = [self.ref]
