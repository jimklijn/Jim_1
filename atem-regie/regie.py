#!/usr/bin/env python3
"""ATEM-regie: automatisch de juiste camera in beeld, op basis van wie er praat.

Gebruik:
  python3 regie.py apparaten              welke audio-interfaces ziet de Mac?
  python3 regie.py geluidscheck           mics meten en advies krijgen
  python3 regie.py start --proef          regie oefenen zonder de ATEM aan te sturen
  python3 regie.py start                  de echte regie
  (voeg --demo toe om te oefenen zonder mics: dan verzint hij een gesprek)
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import re
import select
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from regisseur import RegieInstellingen, Regisseur, Spreker, Wissel

MAP = os.path.dirname(os.path.abspath(__file__))
INSTELLINGEN = os.path.join(MAP, "instellingen.yaml")
LOGBESTAND = os.path.join(MAP, "regie.log")
RAPPORTEN = os.path.join(MAP, "rapporten")

log = logging.getLogger("regie")

MODI = {
    "camera": ("CAMERA'S", "c"),
    "kader": ("PRESENTATIE + SPREKER IN KADER", "k"),
    "naast": ("SPREKER NAAST PRESENTATIE", "n"),
    "presentatie": ("ALLEEN PRESENTATIE", "p"),
}


# ===================================================================== instellingen
@dataclass
class Instellingen:
    atem_ip: str
    overgang: str
    audio_apparaat: str
    sprekers: List[Spreker]
    totaal: int
    presentatie: int
    regie: RegieInstellingen
    start_modus: str
    layouts: Dict[str, object] = field(default_factory=dict)


class FouteInstelling(Exception):
    pass


def laad_instellingen(pad: str = INSTELLINGEN) -> Instellingen:
    import yaml

    from apparaten import Layout

    if not os.path.exists(pad):
        raise FouteInstelling(f"{pad} bestaat niet.")
    try:
        with open(pad, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise FouteInstelling(f"instellingen.yaml is niet goed leesbaar (let op inspringen en dubbele punten):\n{e}")

    def deel(naam):
        waarde = data.get(naam) or {}
        if not isinstance(waarde, dict):
            raise FouteInstelling(f"'{naam}:' in instellingen.yaml is niet goed opgebouwd.")
        return waarde

    atem, audio, camera, regie, layouts = deel("atem"), deel("audio"), deel("camera"), deel("regie"), deel("layouts")

    def ingang(waarde, wat, mag_nul=False):
        try:
            n = int(waarde)
        except (TypeError, ValueError):
            raise FouteInstelling(f"{wat} moet een getal zijn (1-4), nu: {waarde!r}")
        if mag_nul and n == 0:
            return 0
        if not 1 <= n <= 4:
            raise FouteInstelling(f"{wat} moet 1, 2, 3 of 4 zijn (de HDMI-ingangen van de ATEM), nu: {n}")
        return n

    sprekers: List[Spreker] = []
    for i, s in enumerate(data.get("sprekers") or [], start=1):
        if not isinstance(s, dict):
            raise FouteInstelling(f"Spreker {i} in instellingen.yaml is niet goed opgebouwd.")
        naam = str(s.get("naam") or f"Spreker {i}")
        try:
            kanaal = int(s.get("kanaal"))
        except (TypeError, ValueError):
            raise FouteInstelling(f"Spreker '{naam}': 'kanaal' moet een getal zijn (1 = eerste ingang).")
        if kanaal < 1:
            raise FouteInstelling(f"Spreker '{naam}': 'kanaal' begint bij 1.")
        sprekers.append(Spreker(naam, kanaal, ingang(s.get("camera"), f"Camera van '{naam}'"),
                                float(s.get("correctie_db") or 0)))
    if not sprekers:
        raise FouteInstelling("Er staan geen sprekers in instellingen.yaml.")
    namen = [s.naam for s in sprekers]
    if len(set(namen)) != len(namen):
        raise FouteInstelling("Twee sprekers hebben dezelfde naam; geef ze elk een eigen naam.")

    standaard = RegieInstellingen()
    velden = {k: float(regie.get(k, getattr(standaard, k))) for k in standaard.__dataclass_fields__}
    overgang = str(atem.get("overgang") or "cut").lower()
    if overgang not in ("cut", "mix"):
        raise FouteInstelling("atem: overgang moet 'cut' of 'mix' zijn.")
    start_modus = str(data.get("start_modus") or "camera")
    if start_modus not in MODI:
        raise FouteInstelling(f"start_modus moet een van deze zijn: {', '.join(MODI)}")

    lay: Dict[str, object] = {}
    for naam in ("kader", "naast"):
        l = layouts.get(naam)
        if l:
            lay[naam] = Layout(float(l.get("grootte", 0.3)), float(l.get("x", 0)), float(l.get("y", 0)))

    return Instellingen(
        atem_ip=str(atem.get("ip") or "").strip(),
        overgang=overgang,
        audio_apparaat=str(audio.get("apparaat") or "").strip(),
        sprekers=sprekers,
        totaal=ingang(camera.get("totaal", 0), "camera: totaal", mag_nul=True),
        presentatie=ingang(camera.get("presentatie", 0), "camera: presentatie", mag_nul=True),
        regie=RegieInstellingen(**velden),
        start_modus=start_modus,
        layouts=lay,
    )


def zet_logging() -> None:
    logging.basicConfig(
        filename=LOGBESTAND,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# ========================================================================== scherm
class Kleur:
    UIT = "\x1b[0m"
    VET = "\x1b[1m"
    DOF = "\x1b[2m"
    ROOD = "\x1b[31m"
    GROEN = "\x1b[32m"
    GEEL = "\x1b[33m"
    BLAUW = "\x1b[34m"
    CYAAN = "\x1b[36m"


class Toetsenbord:
    """Losse toetsaanslagen lezen zonder Enter (alleen in een echt Terminal-venster)."""

    def __init__(self) -> None:
        self.actief = sys.stdin.isatty()
        self._oud = None

    def __enter__(self):
        if self.actief:
            import termios
            import tty

            self._oud = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *_):
        if self.actief and self._oud is not None:
            import termios

            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._oud)

    def lees(self) -> Optional[str]:
        if not self.actief:
            return None
        klaar, _, _ = select.select([sys.stdin], [], [], 0)
        if klaar:
            return os.read(sys.stdin.fileno(), 1).decode(errors="ignore").lower()
        return None


class Scherm:
    def __init__(self) -> None:
        self.tty = sys.stdout.isatty()

    def __enter__(self):
        if self.tty:
            sys.stdout.write("\x1b[?1049h\x1b[?25l")  # apart scherm, cursor weg
            sys.stdout.flush()
        return self

    def __exit__(self, *_):
        if self.tty:
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()

    def teken(self, regels: List[str]) -> None:
        if not self.tty:
            return
        uit = "\x1b[H" + "".join(r + "\x1b[K\n" for r in regels) + "\x1b[J"
        sys.stdout.write(uit)
        sys.stdout.flush()


def balk(db: float, drempel: Optional[float], breedte: int = 30, kleur: str = "") -> str:
    """Niveaumeter van -60 tot 0 dB, met een streepje op de drempel."""
    def pos(waarde):
        return int(round((min(0.0, max(-60.0, waarde)) + 60.0) / 60.0 * breedte))

    vol = pos(db)
    d = pos(drempel) if drempel is not None else -1
    tekens = []
    for i in range(breedte):
        if i < vol:
            tekens.append(kleur + "█" + Kleur.UIT)
        elif i == d:
            tekens.append(Kleur.DOF + "┆" + Kleur.UIT)
        else:
            tekens.append(Kleur.DOF + "·" + Kleur.UIT)
    return "".join(tekens)


# =========================================================================== bronnen
def maak_bron(inst: Instellingen, demo: bool):
    from apparaten import DemoBron, Niveaumeter

    kanalen = [s.kanaal for s in inst.sprekers]
    if demo:
        return DemoBron(kanalen)
    return Niveaumeter(inst.audio_apparaat, max(kanalen))


def niveaus_uit(meting, kanalen: List[int]) -> Tuple[Dict[int, float], Dict[int, float]]:
    if meting is None:
        return {}, {}
    rms = {k: meting.rms_db[k - 1] for k in kanalen if k - 1 < len(meting.rms_db)}
    piek = {k: meting.piek_db[k - 1] for k in kanalen if k - 1 < len(meting.piek_db)}
    return rms, piek


# ============================================================================ de show
class Show:
    """Koppelt de regisseur aan de ATEM en houdt de modus bij."""

    def __init__(self, atem, regisseur: Regisseur, inst: Instellingen) -> None:
        self.atem = atem
        self.r = regisseur
        self.inst = inst
        self.modus = inst.start_modus
        self.auto = True
        self.geschiedenis: Deque[Tuple[str, str, str]] = deque(maxlen=6)
        self.melding = ""

    def noteer(self, wat: str, reden: str) -> None:
        tijd = dt.datetime.now().strftime("%H:%M:%S")
        self.geschiedenis.appendleft((tijd, wat, reden))
        log.info("%s - %s", wat, reden)
        if not sys.stdout.isatty():
            print(f"{tijd}  {wat:<28} {reden}", flush=True)

    def cameranaam(self, ingang: int) -> str:
        if ingang == self.inst.totaal:
            return f"camera {ingang} (totaal)"
        if ingang == self.inst.presentatie:
            return f"ingang {ingang} (presentatie)"
        return f"camera {ingang}"

    def _veilig(self, actie, *args, **kwargs) -> None:
        try:
            actie(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - de show moet doorgaan
            log.exception("ATEM-opdracht mislukt")
            self.melding = f"ATEM-opdracht mislukt: {e}"

    def toepassen(self) -> None:
        """Zet de hele modus opnieuw neer op de ATEM."""
        shot = self.r.shot
        p = self.inst.presentatie
        if self.modus in ("kader", "naast", "presentatie") and not p:
            self.melding = "Geen presentatie-ingang ingesteld (camera: presentatie in instellingen.yaml)."
            self.modus = "camera"
        if self.modus == "camera":
            self._veilig(self.atem.kader, False)
            self._veilig(self.atem.naar, shot, "cut")
        elif self.modus == "presentatie":
            self._veilig(self.atem.kader, False)
            self._veilig(self.atem.naar, p, "cut")
        elif self.modus == "kader":
            self._veilig(self.atem.naar, p, "cut")
            self._veilig(self.atem.kader, True, shot, self.inst.layouts.get("kader"))
        elif self.modus == "naast":
            self._veilig(self.atem.naar, shot, "cut")
            self._veilig(self.atem.kader, True, p, self.inst.layouts.get("naast"))

    def wissel(self, camera: int) -> None:
        """Alleen de camera wisselen binnen de huidige modus."""
        if self.modus in ("camera", "naast"):
            self._veilig(self.atem.naar, camera)
        elif self.modus == "kader":
            self._veilig(self.atem.kader, True, camera)
        # in 'presentatie' is er geen camera in beeld

    def automatisch(self, w: Wissel) -> None:
        self.wissel(w.camera)
        self.noteer(self.cameranaam(w.camera), w.reden)

    def kies(self, camera: int, t: float) -> None:
        if self.modus == "presentatie":
            self.modus = "camera"
            self.r.forceer(camera, t)
            self.toepassen()
        else:
            self.r.forceer(camera, t)
            self.wissel(camera)
        self.zet_auto(False)
        self.noteer(self.cameranaam(camera), "handmatig")

    def zet_modus(self, modus: str) -> None:
        if modus == self.modus:
            return
        self.modus = modus
        self.toepassen()
        self.noteer(MODI[self.modus][0].lower(), "modus")

    def zet_auto(self, aan: bool) -> None:
        self.auto = aan
        self.r.actief = aan


def start(args) -> int:
    inst = laad_instellingen()
    from apparaten import Atem, ProefAtem

    # Eerst de audio: als daar iets mis is, weet je dat meteen.
    try:
        bron = maak_bron(inst, args.demo)
        bron.start()
    except Exception as e:  # noqa: BLE001
        print(f"Audio starten lukt niet:\n{e}")
        return 1

    if args.proef:
        atem = ProefAtem()
    else:
        if not inst.atem_ip:
            bron.stop()
            print("Vul eerst het IP-adres van de ATEM in bij 'atem: ip:' in instellingen.yaml (zie README).")
            return 1
        atem = Atem(inst.atem_ip, inst.overgang)
        print(f"Verbinden met de ATEM op {inst.atem_ip} ...", flush=True)
        if not atem.verbind():
            atem.stop()
            bron.stop()
            print(
                f"\nGeen verbinding met de ATEM op {inst.atem_ip}.\n"
                "  - Zit er een netwerkkabel in de ATEM, naar dezelfde router als je Mac?\n"
                "  - Klopt het IP-adres? Kijk in Blackmagic ATEM Setup.\n"
                "  - Oefenen zonder ATEM kan met: 3 proefdraaien.command"
            )
            return 1

    start_camera = atem.huidige_camera()
    if start_camera not in {s.camera for s in inst.sprekers} | {inst.totaal}:
        start_camera = inst.totaal or inst.sprekers[0].camera
    regisseur = Regisseur(inst.sprekers, inst.totaal, inst.regie, start_camera)
    show = Show(atem, regisseur, inst)
    show.toepassen()
    show.noteer(MODI[show.modus][0].lower(), "start" + (" (proef)" if args.proef else ""))

    kanalen = sorted({s.kanaal for s in inst.sprekers})
    eind = time.monotonic() + args.duur if args.duur else None
    stil_sinds: Optional[float] = None
    laatst_getekend = 0.0
    bronnaam = getattr(bron, "apparaat_naam", "?")

    try:
        with Scherm() as scherm, Toetsenbord() as toetsen:
            while True:
                t = time.monotonic()
                if eind and t >= eind:
                    break
                meting = bron.meting()
                rms, _ = niveaus_uit(meting, kanalen)
                w = regisseur.update(t, rms)
                if w and show.auto:
                    show.automatisch(w)

                # Waarschuwing als er helemaal niets binnenkomt (vaak: microfoonrechten).
                if rms and max(rms.values()) <= -99:
                    stil_sinds = stil_sinds or t
                else:
                    stil_sinds = None

                toets = toetsen.lees()
                if toets:
                    if toets == "q":
                        break
                    if toets == "a":
                        show.zet_auto(not show.auto)
                        if show.auto:
                            regisseur.forceer(regisseur.shot, t - inst.regie.shot_minimaal)
                        show.noteer("auto " + ("aan" if show.auto else "uit"), "toets")
                    elif toets in "1234":
                        show.kies(int(toets), t)
                    elif toets == "t" and inst.totaal:
                        show.kies(inst.totaal, t)
                    else:
                        for modus, (_, letter) in MODI.items():
                            if toets == letter:
                                show.zet_modus(modus)

                if t - laatst_getekend >= 0.1:
                    laatst_getekend = t
                    scherm.teken(schermregels(show, inst, rms, bronnaam, args, stil_sinds, t))
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        bron.stop()
        atem.stop()

    print("Regie gestopt. Het logboek staat in regie.log.")
    return 0


def schermregels(show: Show, inst: Instellingen, rms, bronnaam, args, stil_sinds, t) -> List[str]:
    r = show.r
    K = Kleur
    nu = dt.datetime.now().strftime("%H:%M:%S")
    verbonden = getattr(show.atem, "verbonden", True)
    atem_tekst = (
        f"{K.GEEL}PROEF (ATEM wordt niet aangestuurd){K.UIT}" if args.proef
        else (f"{K.GROEN}verbonden{K.UIT} ({inst.atem_ip})" if verbonden else f"{K.ROOD}VERBINDING KWIJT{K.UIT}")
    )
    auto_tekst = f"{K.GROEN}{K.VET}AAN{K.UIT}" if show.auto else f"{K.GEEL}{K.VET}UIT (handmatig){K.UIT}"
    sinds = t - r.shot_sinds if r.shot_sinds > -1e9 else 0
    if show.modus == "presentatie":
        in_beeld = f"ingang {inst.presentatie} (presentatie)"
    elif show.modus == "kader":
        in_beeld = f"presentatie, in het kader: {show.cameranaam(r.shot)}"
    elif show.modus == "naast":
        in_beeld = f"{show.cameranaam(r.shot)} met presentatie ernaast"
    else:
        in_beeld = show.cameranaam(r.shot)

    regels = [
        f"{K.VET}ATEM-REGIE{K.UIT}{' ' * 46}{K.DOF}{nu}{K.UIT}",
        f"ATEM: {atem_tekst}    Audio: {bronnaam}" + (f" {K.GEEL}(demo){K.UIT}" if args.demo else ""),
        f"Modus: {K.CYAAN}{K.VET}{MODI[show.modus][0]}{K.UIT}    Auto: {auto_tekst}",
        f"In beeld: {K.VET}{in_beeld}{K.UIT}  {K.DOF}({sinds:.0f} s){K.UIT}",
        "",
    ]
    for s in inst.sprekers:
        st = r.status[s.naam]
        kleur = K.GROEN if st.dominant else (K.GEEL if st.praat else K.DOF)
        label = f"{K.GROEN}{K.VET}● praat{K.UIT}" if st.dominant else ("  ...   " if st.praat else "")
        regels.append(
            f"  {s.naam[:12]:<12} cam {s.camera}  {balk(rms.get(s.kanaal, -100.0), inst.regie.drempel_db, kleur=kleur)}"
            f"  {rms.get(s.kanaal, -100.0):>5.0f} dB  {label}"
        )
    regels.append(f"  {K.DOF}{'':<12}        streepje = drempel ({inst.regie.drempel_db:.0f} dB){K.UIT}")
    regels.append("")
    if stil_sinds and t - stil_sinds > 3:
        regels.append(
            f"{K.ROOD}! Er komt helemaal geen geluid binnen. Geef Terminal toegang tot de microfoon:{K.UIT}"
        )
        regels.append(f"{K.ROOD}  Systeeminstellingen > Privacy en beveiliging > Microfoon > Terminal aan.{K.UIT}")
    if show.melding:
        regels.append(f"{K.ROOD}! {show.melding}{K.UIT}")
    regels.append(f"{K.VET}Laatste wissels{K.UIT}")
    for tijd, wat, reden in show.geschiedenis:
        regels.append(f"  {K.DOF}{tijd}{K.UIT}  {wat:<30} {K.DOF}{reden}{K.UIT}")
    for _ in range(6 - len(show.geschiedenis)):
        regels.append("")
    regels += [
        "",
        f"{K.VET}Toetsen{K.UIT}  [a] auto aan/uit   [1-4] ingang kiezen   [t] totaal   [q] stoppen",
        "         [c] camera's   [k] presentatie + kader   [n] naast elkaar   [p] alleen presentatie",
    ]
    return regels


# ======================================================================= geluidscheck
def geluidscheck(args) -> int:
    from geluidscheck import analyseer

    inst = laad_instellingen()
    try:
        bron = maak_bron(inst, args.demo)
        bron.start()
    except Exception as e:  # noqa: BLE001
        print(f"Audio starten lukt niet:\n{e}")
        return 1
    kanalen = sorted({s.kanaal for s in inst.sprekers})
    stappen = [("stil", None, 6.0)] + [("beurt", s, args.beurt) for s in inst.sprekers]
    stil: Dict[int, List[float]] = {k: [] for k in kanalen}
    beurten: Dict[str, Dict[int, List[float]]] = {s.naam: {k: [] for k in kanalen} for s in inst.sprekers}
    pieken: Dict[int, List[float]] = {k: [] for k in kanalen}
    laatste_tijd = None
    afgebroken = False
    K = Kleur
    try:
        with Scherm() as scherm, Toetsenbord() as toetsen:
            for nr, (soort, spreker, duur) in enumerate(stappen, start=1):
                if hasattr(bron, "zet_praters"):  # demo: speel de stap na
                    bron.zet_praters([] if spreker is None else [spreker.kanaal])
                begin = time.monotonic()
                while True:
                    t = time.monotonic()
                    verstreken = t - begin
                    if verstreken >= duur:
                        break
                    toets = toetsen.lees()
                    if toets == "q":
                        afgebroken = True
                        break
                    if toets in (" ", "\n") and verstreken >= 2.5:  # niet per ongeluk een beurt overslaan
                        break
                    meting = bron.meting()
                    huidig: Dict[int, float] = {}
                    if meting is not None and meting.tijd != laatste_tijd:
                        laatste_tijd = meting.tijd
                        rms, piek = niveaus_uit(meting, kanalen)
                        huidig = rms
                        for k in kanalen:
                            pieken[k].append(piek.get(k, -100.0))
                        if verstreken >= 1.0:  # eerste seconde overslaan: even op gang komen
                            doel = stil if spreker is None else beurten[spreker.naam]
                            for k in kanalen:
                                doel[k].append(rms.get(k, -100.0))
                    if soort == "stil":
                        opdracht = f"{K.VET}Iedereen even helemaal stil.{K.UIT} Dan meten we de ruis."
                    else:
                        opdracht = (f"{K.VET}Nu praat alleen: {K.GROEN}{spreker.naam}{K.UIT}{K.VET}.{K.UIT} "
                                    "Vertel gewoon iets, en lach een keer hardop.")
                    regels = [
                        f"{K.VET}GELUIDSCHECK{K.UIT}   stap {nr} van {len(stappen)}   nog {duur - verstreken:.0f} s"
                        f"   {K.DOF}(spatie = volgende stap, q = stoppen){K.UIT}",
                        f"Audio: {getattr(bron, 'apparaat_naam', '?')}",
                        "",
                        opdracht,
                        "",
                    ]
                    for s in inst.sprekers:
                        reeks = (stil if spreker is None else beurten[spreker.naam])[s.kanaal]
                        nu_db = huidig.get(s.kanaal, reeks[-1] if reeks else -100.0)
                        p = max(pieken[s.kanaal][-10:] or [-100.0])
                        kleur = K.ROOD if p >= -1 else (K.GROEN if nu_db > -35 else K.DOF)
                        pijl = f"{K.GROEN}<- praat nu{K.UIT}" if spreker is s else ""
                        regels.append(f"  {s.naam[:12]:<12} kanaal {s.kanaal}  {balk(nu_db, None, 40, kleur)}"
                                      f"  {nu_db:>5.0f} dB  " + (f"{K.ROOD}TE HARD{K.UIT}" if p >= -1 else pijl))
                    regels += ["", f"{K.DOF}Groen = mooi niveau, rood = vervormt.{K.UIT}"]
                    scherm.teken(regels)
                    time.sleep(0.02)
                if afgebroken:
                    break
    except KeyboardInterrupt:
        afgebroken = True
    finally:
        bron.stop()

    if afgebroken:
        print("Geluidscheck gestopt.")
        return 0
    alles = [v for reeks in stil.values() for v in reeks] + \
        [v for b in beurten.values() for reeks in b.values() for v in reeks]
    if not alles or max(alles) <= -99:
        print("Er kwam geen geluid binnen. Geef Terminal toegang tot de microfoon "
              "(Systeeminstellingen > Privacy en beveiliging > Microfoon) en probeer opnieuw.")
        return 1
    rapport = analyseer([(s.naam, s.kanaal) for s in inst.sprekers], stil, beurten, pieken)
    tekst = rapport.als_tekst()
    print(tekst)
    os.makedirs(RAPPORTEN, exist_ok=True)
    bestand = os.path.join(RAPPORTEN, f"geluidscheck-{dt.datetime.now():%Y%m%d-%H%M}.txt")
    with open(bestand, "w", encoding="utf-8") as f:
        f.write(tekst + "\n")
    print(f"\nRapport bewaard in: {bestand}")

    if rapport.drempel_advies is not None and sys.stdin.isatty() and not args.demo:
        huidig_drempel = inst.regie.drempel_db
        if abs(rapport.drempel_advies - huidig_drempel) >= 2:
            antwoord = input(
                f"\nDrempel van {huidig_drempel:.0f} naar {rapport.drempel_advies:.0f} dB zetten in instellingen.yaml? [j/n] "
            )
            if antwoord.strip().lower().startswith("j"):
                zet_drempel(rapport.drempel_advies)
                print("Opgeslagen.")
    return 0


def zet_drempel(waarde: float, pad: str = INSTELLINGEN) -> None:
    with open(pad, encoding="utf-8") as f:
        tekst = f.read()
    nieuw, aantal = re.subn(r"(?m)^(\s*drempel_db:\s*)-?\d+(?:\.\d+)?", rf"\g<1>{waarde:.0f}", tekst, count=1)
    if aantal:
        with open(pad, "w", encoding="utf-8") as f:
            f.write(nieuw)


# =========================================================================== apparaten
def apparaten(_args) -> int:
    from apparaten import lijst_invoerapparaten

    lijst = lijst_invoerapparaten()
    if not lijst:
        print("Geen audio-invoer gevonden.")
        return 1
    print("Audio-invoer die de Mac ziet:\n")
    for a in lijst:
        print(f"  {a['naam']:<40} {a['kanalen']:>2} kanalen   {int(a['samplerate'])} Hz")
    print("\nZet (een deel van) de naam van je audio-interface bij 'audio: apparaat:' in instellingen.yaml.")
    return 0


# ================================================================================ main
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Automatische regie voor de ATEM Mini Pro.")
    sub = parser.add_subparsers(dest="opdracht", required=True)
    sub.add_parser("apparaten", help="laat zien welke audio-interfaces de Mac ziet")
    g = sub.add_parser("geluidscheck", help="mics meten en advies krijgen")
    g.add_argument("--demo", action="store_true", help="verzonnen geluid, zonder mics")
    g.add_argument("--beurt", type=float, default=8, help="seconden per spreker (standaard 8)")
    s = sub.add_parser("start", help="de regie starten")
    s.add_argument("--proef", action="store_true", help="ATEM niet aansturen, alleen laten zien")
    s.add_argument("--demo", action="store_true", help="verzonnen gesprek, zonder mics")
    s.add_argument("--duur", type=float, default=0, help="na zoveel seconden vanzelf stoppen")
    args = parser.parse_args(argv)

    zet_logging()
    try:
        return {"apparaten": apparaten, "geluidscheck": geluidscheck, "start": start}[args.opdracht](args)
    except FouteInstelling as e:
        print(f"Probleem in instellingen.yaml:\n  {e}")
        return 1
    except RuntimeError as e:
        print(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
