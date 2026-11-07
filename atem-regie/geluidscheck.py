"""Analyse van een geluidscheck: hoe staan de mics afgesteld, en welk advies volgt daaruit.

De check gaat in stappen:
  1. iedereen is even stil            -> ruis per mic
  2. iedereen praat om de beurt        -> praatniveau per mic, overspraak naar de andere mics,
                                          en of elke mic op het goede kanaal binnenkomt
Dit bestand rekent alleen. Het opnemen en tonen gebeurt in regie.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Richtwaarden voor het niveau tijdens praten (gemiddeld over blokjes van 50 ms).
TE_ZACHT = -32.0
TE_HARD = -9.0
CLIP = -1.0  # pieken hierboven = vervorming
WEINIG_VERSCHIL = 10.0  # praten nauwelijks harder dan stilte: mic uit of verkeerd kanaal
VEEL_RUIS = -50.0
ONGELIJK = 6.0  # verschil tussen mics waarboven we gelijktrekken aanraden
GEKOPPELD = 4.0  # buurman-mic bijna even hard als de eigen mic: kanalen gekoppeld
WEINIG_SCHEIDING = 10.0  # buurman-mic hoort je bijna even hard: regie wordt onzeker


def percentiel(waarden: List[float], p: float) -> float:
    if not waarden:
        return -100.0
    s = sorted(waarden)
    k = (len(s) - 1) * p / 100.0
    onder = int(k)
    boven = min(onder + 1, len(s) - 1)
    return s[onder] + (s[boven] - s[onder]) * (k - onder)


@dataclass
class MicResultaat:
    naam: str
    kanaal: int
    ruis: float = -100.0
    spraak: float = -100.0
    piek: float = -100.0
    clips: int = 0
    overspraak: float = -100.0  # hoe hard deze mic de anderen hoort
    oordeel: str = "goed"  # goed / zacht / hard / uit
    adviezen: List[str] = field(default_factory=list)

    @property
    def bruikbaar(self) -> bool:
        return self.oordeel != "uit"


@dataclass
class Rapport:
    mics: List[MicResultaat]
    algemeen: List[str]
    drempel_advies: Optional[float]
    correcties: Dict[str, float]

    def als_tekst(self) -> str:
        regels = ["GELUIDSCHECK", "=" * 66, ""]
        regels.append(f"{'Mic':<14}{'kanaal':>7}{'stil':>8}{'praten':>9}{'piek':>8}{'buren':>8}   oordeel")
        for m in self.mics:
            regels.append(
                f"{m.naam[:13]:<14}{m.kanaal:>7}{m.ruis:>6.0f}dB{m.spraak:>7.0f}dB{m.piek:>6.0f}dB"
                f"{m.overspraak:>6.0f}dB   {m.oordeel.upper()}"
            )
        regels.append(f"{'':<14}{'':>7}  {'(buren = hoe hard deze mic de anderen hoort)'}")
        regels.append("")
        regels.append("Advies per mic:")
        for m in self.mics:
            if m.adviezen:
                for a in m.adviezen:
                    regels.append(f"  - {m.naam}: {a}")
            else:
                regels.append(f"  - {m.naam}: in orde.")
        if self.algemeen:
            regels.append("")
            regels.append("Algemeen:")
            for a in self.algemeen:
                regels.append(f"  - {a}")
        if self.drempel_advies is not None:
            regels.append("")
            regels.append(f"Aanbevolen drempel voor de regie: drempel_db: {self.drempel_advies:.0f}")
        if self.correcties:
            regels.append("")
            regels.append("Liever aan de knoppen draaien (gain). Lukt dat niet, zet dan bij de spreker in instellingen.yaml:")
            for naam, c in self.correcties.items():
                regels.append(f"  {naam}: correctie_db: {c:+.0f}")
        return "\n".join(regels)


def analyseer(
    mics: List[Tuple[str, int]],
    stil: Dict[int, List[float]],
    beurten: Dict[str, Dict[int, List[float]]],
    piek: Dict[int, List[float]],
) -> Rapport:
    """
    mics    = [(naam, kanaal)]
    stil    = {kanaal: [dB]}                gemeten terwijl iedereen stil was
    beurten = {naam: {kanaal: [dB]}}        gemeten terwijl alleen 'naam' praatte
    piek    = {kanaal: [dB]}                alle pieken van de hele check
    """
    resultaten: List[MicResultaat] = []
    algemeen: List[str] = []

    for naam, kanaal in mics:
        res = MicResultaat(naam=naam, kanaal=kanaal)
        res.ruis = percentiel(stil.get(kanaal, []), 50)
        eigen = beurten.get(naam, {}).get(kanaal, [])
        res.spraak = percentiel(eigen, 90)
        p = piek.get(kanaal, [])
        res.piek = max(p) if p else -100.0
        res.clips = sum(1 for v in p if v >= CLIP)
        anderen = [percentiel(b.get(kanaal, []), 90) for n, b in beurten.items() if n != naam and b.get(kanaal)]
        res.overspraak = max(anderen) if anderen else -100.0

        verschil = res.spraak - res.ruis
        if not eigen:
            res.oordeel = "uit"
            res.adviezen.append("niet gemeten: deze beurt is overgeslagen. Doe de check opnieuw.")
        elif verschil < WEINIG_VERSCHIL:
            res.oordeel = "uit"
            res.adviezen.append(
                f"praten is nauwelijks harder dan stilte ({verschil:.0f} dB verschil). Staat de mic aan, "
                f"is de zender verbonden, en komt deze mic echt binnen op kanaal {kanaal}?"
            )
        elif res.clips > 0 or res.spraak > TE_HARD:
            res.oordeel = "hard"
            if res.clips:
                res.adviezen.append(f"te hard, het geluid vervormt ({res.clips}x). Zet de gain lager.")
            else:
                res.adviezen.append("erg hard. Zet de gain iets lager, dan is er ruimte voor lachen of roepen.")
        elif res.spraak < TE_ZACHT:
            res.oordeel = "zacht"
            res.adviezen.append(
                f"vrij zacht (praten rond {res.spraak:.0f} dB, mik op -24 tot -15). "
                "Zet de gain hoger of draag de mic iets dichter bij de mond."
            )
        if res.oordeel != "uit" and res.ruis > VEEL_RUIS:
            res.adviezen.append(
                f"veel ruis of achtergrondgeluid als het stil is ({res.ruis:.0f} dB). Mic dichter bij de mond, "
                "gain op de zender omhoog en op de interface omlaag, of zet ventilatoren en airco uit."
            )
        resultaten.append(res)

    # Komt elke stem op het eigen kanaal binnen?
    kanaal_van = {naam: kanaal for naam, kanaal in mics}
    for naam, metingen in beurten.items():
        if naam not in kanaal_van or not metingen:
            continue
        niveaus = {k: percentiel(v, 90) for k, v in metingen.items() if v}
        if not niveaus:
            continue
        hardste = max(niveaus, key=niveaus.get)
        eigen = kanaal_van[naam]
        if hardste != eigen and niveaus[hardste] - niveaus.get(eigen, -100.0) > 3:
            wie = [n for n, k in mics if k == hardste]
            algemeen.append(
                f"Toen {naam} praatte, was kanaal {hardste} het hardst, niet kanaal {eigen}. "
                + (f"Waarschijnlijk zijn de mics van {naam} en {wie[0]} omgewisseld. " if wie else "")
                + "Wissel de kanalen om in instellingen.yaml (of wissel de zenders om)."
            )

    # Hoort de buurman-mic je bijna net zo hard? Dan kan de regie niet horen wie er praat.
    for res in resultaten:
        if not res.bruikbaar:
            continue
        for ander in resultaten:
            if ander is res or not ander.bruikbaar:
                continue
            buur = percentiel(beurten.get(res.naam, {}).get(ander.kanaal, []), 90)
            scheiding = res.spraak - buur
            if scheiding < GEKOPPELD:
                algemeen.append(
                    f"Toen {res.naam} praatte, kwam dat op kanaal {ander.kanaal} ({ander.naam}) bijna even hard binnen. "
                    "Waarschijnlijk stuurt de ontvanger één mix door, of staan de ingangen gekoppeld (stereo-link). "
                    "Zet de ontvanger op aparte kanalen (vaak 'mono', 'split' of 'safety off')."
                )
            elif scheiding < WEINIG_SCHEIDING:
                algemeen.append(
                    f"De mic van {ander.naam} pikt {res.naam} behoorlijk op (maar {scheiding:.0f} dB zachter). "
                    f"Zit {ander.naam} dicht bij {res.naam}? Een mic iets hoger op de borst helpt."
                )

    # Mics onderling gelijktrekken.
    correcties: Dict[str, float] = {}
    goed = [m for m in resultaten if m.bruikbaar]
    if len(goed) >= 2:
        midden = percentiel([m.spraak for m in goed], 50)
        hardste = max(goed, key=lambda m: m.spraak)
        zachtste = min(goed, key=lambda m: m.spraak)
        if hardste.spraak - zachtste.spraak > ONGELIJK:
            algemeen.append(
                f"De mics staan ongelijk: {hardste.naam} is {hardste.spraak - zachtste.spraak:.0f} dB harder dan "
                f"{zachtste.naam}. Trek ze gelijk met de gain, dan klinkt het in de stream ook rustiger."
            )
            for m in goed:
                c = round(midden - m.spraak)
                if abs(c) >= 3:
                    correcties[m.naam] = float(c)

    # Drempel: tussen de hardste stilte en het zachtste praten in.
    drempel: Optional[float] = None
    if goed:
        hoogste_ruis = max(m.ruis for m in goed)
        laagste_spraak = min(m.spraak for m in goed)
        ruimte = laagste_spraak - hoogste_ruis
        drempel = float(round(hoogste_ruis + ruimte * 0.5))
        if ruimte < 15:
            algemeen.append(
                "Er zit weinig verschil tussen praten en stilte. De regie werkt dan minder betrouwbaar; "
                "los eerst de adviezen hierboven op en doe de check opnieuw."
            )
    else:
        algemeen.append("Geen enkele mic gaf bruikbaar geluid. Kijk of de goede interface in instellingen.yaml staat.")

    # Dubbele meldingen (A->B en B->A) maar één keer tonen.
    gezien, uniek = set(), []
    for a in algemeen:
        if a not in gezien:
            gezien.add(a)
            uniek.append(a)
    return Rapport(resultaten, uniek, drempel, correcties)
