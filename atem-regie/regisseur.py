"""De regisseur: beslist op basis van microfoonniveaus welke camera in beeld hoort.

Dit bestand praat niet met de ATEM en niet met de audio-interface. Het krijgt
alleen niveaus binnen (in dB) en zegt wanneer er gewisseld moet worden. Daardoor
is het los te testen (zie tests/test_regisseur.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

STIL_DB = -100.0  # niveau dat we gebruiken voor 'helemaal niets'


@dataclass
class Spreker:
    naam: str
    kanaal: int  # 1 = eerste ingang van de audio-interface
    camera: int  # HDMI-ingang van de ATEM (1-4)
    correctie_db: float = 0.0  # om zachte/harde mics gelijk te trekken


@dataclass
class RegieInstellingen:
    drempel_db: float = -42.0  # vanaf dit niveau telt iemand als 'aan het praten'
    dominant_db: float = 6.0  # zoveel harder dan de rest = 'de spreker'
    praat_minimaal: float = 1.2  # sec praten voordat er naar iemand gewisseld wordt
    shot_minimaal: float = 4.0  # sec dat een shot minstens blijft staan
    totaal_bij_stilte: float = 4.0  # sec stilte en dan het totaalshot (0 = nooit)
    totaal_bij_door_elkaar: float = 2.0  # sec door elkaar praten en dan totaal (0 = nooit)
    afwisselen_na: float = 0.0  # na zoveel sec op één spreker even totaal (0 = uit)
    pauze_tolerantie: float = 0.45  # korte stiltes tussen woorden tellen nog als praten
    demping: float = 0.30  # sec; hoe rustig de niveaus worden afgevlakt


@dataclass
class SprekerStatus:
    niveau_db: float = STIL_DB  # afgevlakt niveau (na correctie)
    laatst_luid: float = -math.inf
    praat: bool = False
    dominant: bool = False


@dataclass
class Wissel:
    tijd: float
    camera: int
    reden: str


DOOR_ELKAAR = "door_elkaar"


class Regisseur:
    """Houdt bij wie er praat en beslist wanneer er gewisseld wordt.

    Gebruik: roep `update(t, niveaus)` een keer of 10-20 per seconde aan. Als er
    gewisseld moet worden, geeft hij een `Wissel` terug, anders None.
    """

    def __init__(
        self,
        sprekers: List[Spreker],
        totaal_camera: int,
        instellingen: RegieInstellingen,
        start_camera: Optional[int] = None,
    ) -> None:
        if not sprekers:
            raise ValueError("Er moet minstens één spreker zijn.")
        self.sprekers = sprekers
        self.totaal_camera = totaal_camera or 0
        self.inst = instellingen
        self.status: Dict[str, SprekerStatus] = {s.naam: SprekerStatus() for s in sprekers}
        self.shot: int = start_camera or self.totaal_camera or sprekers[0].camera
        self.shot_sinds: float = -math.inf
        self.actief: bool = True
        self.kandidaat: Optional[object] = None  # camera-nummer, DOOR_ELKAAR of None (stil)
        self.scores: Dict[object, float] = {}
        self.stil_duur: float = 0.0
        self.vorige_t: Optional[float] = None

    # ------------------------------------------------------------------ helpers
    def camera_van(self, naam: str) -> int:
        for s in self.sprekers:
            if s.naam == naam:
                return s.camera
        raise KeyError(naam)

    def wie_praat(self) -> List[str]:
        return [s.naam for s in self.sprekers if self.status[s.naam].dominant]

    def forceer(self, camera: int, t: float) -> None:
        """Handmatig gekozen camera: onthoud hem en begin de tellers opnieuw."""
        self.shot = camera
        self.shot_sinds = t
        self.scores.clear()
        self.stil_duur = 0.0

    # --------------------------------------------------------------- de kern
    def update(self, t: float, niveaus: Dict[int, float]) -> Optional[Wissel]:
        """Verwerk nieuwe niveaus. `niveaus` = {kanaal: dB}."""
        dt = 0.0 if self.vorige_t is None else max(0.0, t - self.vorige_t)
        self.vorige_t = t
        inst = self.inst

        # 1. Niveaus afvlakken en bepalen wie er praat.
        alpha = 1.0 if dt == 0 else 1.0 - math.exp(-dt / max(inst.demping, 1e-3))
        for s in self.sprekers:
            st = self.status[s.naam]
            ruw = niveaus.get(s.kanaal, STIL_DB) + s.correctie_db
            st.niveau_db = ruw if st.niveau_db <= STIL_DB else st.niveau_db + alpha * (ruw - st.niveau_db)
            if ruw >= inst.drempel_db:
                st.laatst_luid = t
            st.praat = (t - st.laatst_luid) <= inst.pauze_tolerantie

        praters = [s for s in self.sprekers if self.status[s.naam].praat]
        luidste = max((self.status[s.naam].niveau_db for s in praters), default=STIL_DB)
        cameras = set()
        for s in self.sprekers:
            st = self.status[s.naam]
            st.dominant = st.praat and st.niveau_db >= luidste - inst.dominant_db
            if st.dominant:
                cameras.add(s.camera)

        # 2. Wat zou er nu in beeld moeten?
        if not cameras:
            kandidaat: Optional[object] = None
        elif len(cameras) == 1:
            kandidaat = next(iter(cameras))
        else:
            kandidaat = DOOR_ELKAAR
        self.kandidaat = kandidaat

        # 3. Tellers bijwerken. Wie in beeld wil, bouwt punten op; de rest zakt weg.
        #    Zo zorgt een kort "ja" of "hm" niet meteen voor een wissel.
        for k in list(self.scores):
            if k != kandidaat:
                self.scores[k] = max(0.0, self.scores[k] - dt)
        if kandidaat is not None:
            # Begrensd op de drempel: wie lang heeft gepraat, bouwt geen 'tegoed' op
            # waarmee een later kort "hm" alsnog meteen een wissel zou geven.
            plafond = inst.totaal_bij_door_elkaar if kandidaat == DOOR_ELKAAR else inst.praat_minimaal
            self.scores[kandidaat] = min(self.scores.get(kandidaat, 0.0) + dt, max(plafond, 0.0))
        self.stil_duur = self.stil_duur + dt if kandidaat is None else 0.0

        # 4. Doel bepalen.
        doel, reden = self.shot, ""
        if isinstance(kandidaat, int) and self.scores.get(kandidaat, 0.0) >= inst.praat_minimaal:
            if kandidaat != self.shot:
                doel, reden = kandidaat, self._namen_bij(kandidaat) + " praat"
            elif (
                inst.afwisselen_na > 0
                and self.totaal_camera
                and self.shot != self.totaal_camera
                and t - self.shot_sinds >= inst.afwisselen_na
            ):
                doel, reden = self.totaal_camera, "afwisseling"
        elif (
            kandidaat == DOOR_ELKAAR
            and self.totaal_camera
            and inst.totaal_bij_door_elkaar > 0
            and self.scores.get(DOOR_ELKAAR, 0.0) >= inst.totaal_bij_door_elkaar
        ):
            doel, reden = self.totaal_camera, "door elkaar"
        elif (
            kandidaat is None
            and self.totaal_camera
            and inst.totaal_bij_stilte > 0
            and self.stil_duur >= inst.totaal_bij_stilte
        ):
            doel, reden = self.totaal_camera, "stilte"

        # 5. Wisselen, als het mag.
        if not self.actief or doel == self.shot:
            return None
        if t - self.shot_sinds < inst.shot_minimaal:
            return None
        self.shot = doel
        self.shot_sinds = t
        return Wissel(tijd=t, camera=doel, reden=reden)

    def _namen_bij(self, camera: int) -> str:
        namen = [s.naam for s in self.sprekers if s.camera == camera and self.status[s.naam].dominant]
        return " + ".join(namen) if namen else f"camera {camera}"
