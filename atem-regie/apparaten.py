"""De koppeling met de buitenwereld: de ATEM (via het netwerk) en de audio-interface.

Er zijn ook nep-versies voor oefenen zonder spullen:
- ProefAtem: doet alsof, verstuurt niets naar de ATEM.
- DemoBron: verzint een gesprek, zodat je de regie kunt zien werken zonder mics.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

log = logging.getLogger("regie")

STIL_DB = -100.0


# ============================================================================ ATEM
@dataclass
class Layout:
    """Positie en grootte van het beeld-in-beeld-kader, in dezelfde getallen als
    ATEM Software Control (Position X/Y en Size)."""

    grootte: float
    x: float
    y: float


class Atem:
    """Bestuurt de ATEM Mini Pro via het netwerk (er is een netwerkkabel nodig)."""

    ME = 0  # de ATEM Mini Pro heeft één mix-effectbus
    KEYER = 0  # en één 'upstream keyer' voor beeld-in-beeld

    def __init__(self, ip: str, overgang: str = "cut") -> None:
        import PyATEMMax  # pas hier importeren: dan werkt proefmodus ook zonder

        self.ip = ip
        self.overgang = overgang
        self.sw = PyATEMMax.ATEMMax()
        self.sw.setLogLevel(logging.WARNING)
        self.sw.setSocketLogLevel(logging.WARNING)
        self.proef = False

    def verbind(self, timeout: float = 6.0) -> bool:
        self.sw.connect(self.ip)
        ok = bool(self.sw.waitForConnection(infinite=False, timeout=timeout))
        if ok and self.overgang == "mix":
            self.sw.setTransitionStyle(self.ME, "mix")
        return ok

    @property
    def verbonden(self) -> bool:
        return bool(self.sw.connected)

    def huidige_camera(self) -> Optional[int]:
        try:
            bron = self.sw.programInput[self.ME].videoSource
            waarde = getattr(bron, "value", bron)
            return int(waarde) if 1 <= int(waarde) <= 8 else None
        except Exception:  # noqa: BLE001 - status nog niet binnen
            return None

    def naar(self, ingang: int, overgang: Optional[str] = None) -> None:
        """Zet een ingang in beeld (program)."""
        if (overgang or self.overgang) == "mix":
            self.sw.setPreviewInputVideoSource(self.ME, ingang)
            time.sleep(0.03)
            self.sw.execAutoME(self.ME)
        else:
            self.sw.setProgramInputVideoSource(self.ME, ingang)

    def kader(self, aan: bool, bron: Optional[int] = None, layout: Optional[Layout] = None) -> None:
        """Beeld-in-beeld: bron = wat er in het kader staat."""
        if bron is not None:
            self.sw.setKeyerFillSource(self.ME, self.KEYER, bron)
        if layout is not None:
            self.sw.setKeyerType(self.ME, self.KEYER, "dVE")
            self.sw.setKeyDVESizeX(self.ME, self.KEYER, layout.grootte)
            self.sw.setKeyDVESizeY(self.ME, self.KEYER, layout.grootte)
            self.sw.setKeyDVEPositionX(self.ME, self.KEYER, layout.x)
            self.sw.setKeyDVEPositionY(self.ME, self.KEYER, layout.y)
        self.sw.setKeyerOnAirEnabled(self.ME, self.KEYER, aan)

    def stop(self) -> None:
        try:
            self.sw.disconnect()
        except Exception:  # noqa: BLE001
            pass


class ProefAtem:
    """Doet alsof hij een ATEM is. Handig om de regie te testen zonder risico."""

    def __init__(self, melder: Optional[Callable[[str], None]] = None) -> None:
        self.ip = "proefmodus"
        self.proef = True
        self.verbonden = True
        self.melder = melder or (lambda tekst: None)
        self._camera: Optional[int] = None

    def verbind(self, timeout: float = 0) -> bool:
        return True

    def huidige_camera(self) -> Optional[int]:
        return self._camera

    def naar(self, ingang: int, overgang: Optional[str] = None) -> None:
        self._camera = ingang
        log.info("[proef] program -> ingang %s", ingang)

    def kader(self, aan: bool, bron: Optional[int] = None, layout: Optional[Layout] = None) -> None:
        log.info("[proef] kader %s, bron %s, layout %s", "aan" if aan else "uit", bron, layout)

    def stop(self) -> None:
        pass


# =========================================================================== AUDIO
def naar_db(waarde: float) -> float:
    if waarde <= 1e-5:
        return STIL_DB
    return max(STIL_DB, 20.0 * math.log10(waarde))


@dataclass
class Meting:
    rms_db: List[float]  # gemiddeld niveau per kanaal over het laatste blokje
    piek_db: List[float]  # hoogste piek per kanaal
    tijd: float


def lijst_invoerapparaten() -> List[dict]:
    import sounddevice as sd

    uit = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            uit.append({"index": i, "naam": d["name"], "kanalen": d["max_input_channels"],
                        "samplerate": d["default_samplerate"]})
    return uit


class Niveaumeter:
    """Leest de niveaus van de audio-interface op de Mac. OBS en andere programma's
    kunnen tegelijk dezelfde interface gebruiken; dit programma luistert alleen mee."""

    def __init__(self, apparaat: str, kanalen_nodig: int, blokduur: float = 0.05) -> None:
        import numpy as np  # noqa: F401  - meteen falen als het ontbreekt
        import sounddevice as sd

        self._sd = sd
        self.kanalen_nodig = kanalen_nodig
        self.blokduur = blokduur
        self.apparaat_index, self.apparaat_naam, self.kanalen_beschikbaar = self._zoek(apparaat)
        if self.kanalen_beschikbaar < kanalen_nodig:
            raise RuntimeError(
                f"'{self.apparaat_naam}' geeft maar {self.kanalen_beschikbaar} kanaal/kanalen door, "
                f"maar in instellingen.yaml gebruik je kanaal {kanalen_nodig}. "
                "Controleer of je de goede interface hebt gekozen en of alle ingangen aanstaan."
            )
        self._lock = threading.Lock()
        self._laatste: Optional[Meting] = None
        self._stream = None

    def _zoek(self, naam: str):
        apparaten = lijst_invoerapparaten()
        if not apparaten:
            raise RuntimeError("Geen enkel audio-invoerapparaat gevonden.")
        if naam:
            for a in apparaten:
                if naam.lower() in a["naam"].lower():
                    return a["index"], a["naam"], a["kanalen"]
            namen = "\n".join(f"  - {a['naam']} ({a['kanalen']} kanalen)" for a in apparaten)
            raise RuntimeError(
                f"Audio-interface '{naam}' niet gevonden. Deze apparaten zijn er wel:\n{namen}\n"
                "Zet (een deel van) de juiste naam bij 'audio: apparaat:' in instellingen.yaml."
            )
        index = self._sd.default.device[0]
        info = self._sd.query_devices(index)
        return index, info["name"], info["max_input_channels"]

    def start(self) -> None:
        import numpy as np

        info = self._sd.query_devices(self.apparaat_index)
        samplerate = int(info["default_samplerate"]) or 48000
        blok = max(64, int(samplerate * self.blokduur))

        def callback(indata, frames, tijd, status):  # draait in een aparte thread
            if status:
                log.debug("audio-status: %s", status)
            data = indata.astype(np.float64, copy=False)
            rms = np.sqrt(np.mean(np.square(data), axis=0))
            piek = np.max(np.abs(data), axis=0)
            meting = Meting([naar_db(float(v)) for v in rms], [naar_db(float(v)) for v in piek], time.monotonic())
            with self._lock:
                self._laatste = meting

        self._stream = self._sd.InputStream(
            device=self.apparaat_index,
            channels=self.kanalen_nodig,
            samplerate=samplerate,
            blocksize=blok,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()
        log.info("Audio: luister naar '%s', %d kanalen, %d Hz", self.apparaat_naam, self.kanalen_nodig, samplerate)

    def meting(self) -> Optional[Meting]:
        with self._lock:
            return self._laatste

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class DemoBron:
    """Verzint een gesprek tussen de sprekers: beurten, korte reacties, door elkaar
    praten en stiltes. Zo zie je wat de regie doet zonder echte microfoons."""

    PRAAT, OVERSPRAAK, RUIS = -22.0, -40.0, -62.0

    def __init__(self, kanalen: List[int], zaad: Optional[int] = None) -> None:
        self.kanalen = sorted(set(kanalen))
        self.apparaat_naam = "demo (verzonnen gesprek)"
        self._rnd = random.Random(zaad)
        self._start = time.monotonic()
        self._plan: List[tuple] = []  # (eindtijd, [kanalen die praten])
        self._klaar_tot = 0.0
        self._vast: Optional[List[int]] = None  # voor de geluidscheck: wie praat er nu

    def zet_praters(self, kanalen: Optional[List[int]]) -> None:
        self._vast = kanalen

    def _plan_aanvullen(self, tot: float) -> None:
        r = self._rnd
        while self._klaar_tot < tot:
            keuze = r.random()
            if keuze < 0.62:
                duur, praters = r.uniform(4, 12), [r.choice(self.kanalen)]
            elif keuze < 0.80:
                duur, praters = r.uniform(0.3, 0.7), [r.choice(self.kanalen)]  # kort "ja"
            elif keuze < 0.90 and len(self.kanalen) > 1:
                duur, praters = r.uniform(2.5, 5), r.sample(self.kanalen, 2)  # door elkaar
            else:
                duur, praters = r.uniform(1, 6), []  # stilte
            self._klaar_tot += duur
            self._plan.append((self._klaar_tot, praters))

    def start(self) -> None:
        self._start = time.monotonic()

    def meting(self) -> Optional[Meting]:
        nu = time.monotonic() - self._start
        self._plan_aanvullen(nu + 1)
        praters: List[int] = []
        if self._vast is not None:
            praters = self._vast
        else:
            for eind, p in self._plan:
                if eind >= nu:
                    praters = p
                    break
        hoogste = max(self.kanalen)
        rms = []
        for k in range(1, hoogste + 1):
            if k in praters:
                basis = self.PRAAT
            elif praters:
                basis = self.OVERSPRAAK
            else:
                basis = self.RUIS
            # spraak golft op en neer, met af en toe een adempauze
            golf = 5 * math.sin(nu * 7.3 + k) * (1 if k in praters else 0.3)
            rms.append(basis + golf + self._rnd.uniform(-2, 2))
        return Meting(rms, [v + 9 for v in rms], time.monotonic())

    def stop(self) -> None:
        pass
