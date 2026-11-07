"""Tests voor de regisseur. Draaien met:  python3 -m unittest discover -s tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from regisseur import RegieInstellingen, Regisseur, Spreker  # noqa: E402

PRAAT = -20.0  # iemand praat in zijn eigen mic
OVERSPRAAK = -38.0  # dezelfde stem, opgevangen door de mic van de buurman
STIL = -65.0  # ruis van een mic waar niemand in praat
STAP = 0.05  # 20 metingen per seconde, net als in het echt


def niveaus(praters=(), overspraak=True):
    """Niveaus voor 4 kanalen: de praters hard, de rest stil of met overspraak."""
    uit = {}
    for kanaal in (1, 2, 3, 4):
        if kanaal in praters:
            uit[kanaal] = PRAAT
        elif praters and overspraak:
            uit[kanaal] = OVERSPRAAK
        else:
            uit[kanaal] = STIL
    return uit


class Simulatie:
    def __init__(self, **instellingen):
        self.sprekers = [
            Spreker("Jim", 1, 1),
            Spreker("Gast 1", 2, 2),
            Spreker("Gast 2", 3, 2),  # zit naast Gast 1: zelfde camera
            Spreker("Gast 3", 4, 1),
        ]
        inst = RegieInstellingen(**instellingen)
        self.r = Regisseur(self.sprekers, totaal_camera=3, instellingen=inst, start_camera=3)
        self.t = 0.0
        self.wissels = []

    def speel(self, seconden, praters=(), **kw):
        stappen = int(round(seconden / STAP))
        for _ in range(stappen):
            self.t += STAP
            w = self.r.update(self.t, niveaus(praters, **kw))
            if w:
                self.wissels.append(w)
        return self

    @property
    def cameras(self):
        return [w.camera for w in self.wissels]


class TestRegisseur(unittest.TestCase):
    def test_spreker_komt_in_beeld_na_praat_minimaal(self):
        sim = Simulatie(praat_minimaal=1.0)
        sim.speel(0.8, praters=[1])
        self.assertEqual(sim.cameras, [], "na 0,8 s nog niet wisselen")
        sim.speel(0.5, praters=[1])
        self.assertEqual(sim.cameras, [1])
        self.assertIn("Jim", sim.wissels[0].reden)

    def test_kort_ja_geeft_geen_wissel(self):
        sim = Simulatie()
        sim.speel(6, praters=[1])
        sim.speel(0.5, praters=[2])  # "ja"
        sim.speel(6, praters=[1])
        self.assertEqual(sim.cameras, [1])

    def test_shot_blijft_minimaal_staan(self):
        sim = Simulatie(shot_minimaal=4.0, praat_minimaal=1.0)
        sim.speel(1.5, praters=[1])  # wissel naar 1 op ~1,0 s
        sim.speel(2.0, praters=[2])  # Gast 1 praat al lang genoeg, maar shot nog te kort
        self.assertEqual(sim.cameras, [1])
        sim.speel(2.0, praters=[2])
        self.assertEqual(sim.cameras, [1, 2])
        self.assertGreaterEqual(sim.wissels[1].tijd - sim.wissels[0].tijd, 4.0)

    def test_overspraak_telt_niet_als_praten(self):
        sim = Simulatie()
        sim.speel(8, praters=[2], overspraak=True)
        self.assertEqual(sim.cameras, [2])

    def test_twee_sprekers_op_dezelfde_camera_is_geen_door_elkaar(self):
        sim = Simulatie(praat_minimaal=1.0)
        sim.speel(6, praters=[2, 3])
        self.assertEqual(sim.cameras, [2])

    def test_door_elkaar_gaat_naar_totaal(self):
        sim = Simulatie(totaal_bij_door_elkaar=2.0)
        sim.speel(6, praters=[1])
        sim.speel(4, praters=[1, 2])
        self.assertEqual(sim.cameras, [1, 3])
        self.assertEqual(sim.wissels[-1].reden, "door elkaar")

    def test_stilte_gaat_naar_totaal(self):
        sim = Simulatie(totaal_bij_stilte=3.0)
        sim.speel(6, praters=[2])
        sim.speel(2.5)
        self.assertEqual(sim.cameras, [2])
        sim.speel(1.5)
        self.assertEqual(sim.cameras, [2, 3])
        self.assertEqual(sim.wissels[-1].reden, "stilte")

    def test_pauze_tussen_woorden_blijft_praten(self):
        sim = Simulatie(praat_minimaal=1.5)
        # Praten met korte haperingen van 0,3 s: moet als doorlopend praten tellen.
        for _ in range(4):
            sim.speel(0.5, praters=[2])
            sim.speel(0.3)
        self.assertEqual(sim.cameras, [2])

    def test_lang_praten_bouwt_geen_tegoed_op(self):
        sim = Simulatie(praat_minimaal=1.0, shot_minimaal=2.0)
        sim.speel(30, praters=[1])  # Jim praat lang
        sim.speel(3, praters=[2])  # Gast 1 neemt het over
        sim.speel(0.4, praters=[1])  # Jim zegt kort "hm"
        sim.speel(3, praters=[2])
        self.assertEqual(sim.cameras, [1, 2])

    def test_afwisseling_bij_lange_monoloog(self):
        sim = Simulatie(afwisselen_na=10.0, shot_minimaal=4.0)
        sim.speel(30, praters=[1])
        self.assertEqual(sim.cameras[:3], [1, 3, 1])
        self.assertEqual(sim.wissels[1].reden, "afwisseling")

    def test_zonder_totaalcamera_blijft_het_huidige_shot(self):
        sim = Simulatie()
        sim.r.totaal_camera = 0
        sim.speel(6, praters=[1])
        sim.speel(10)  # stilte
        sim.speel(5, praters=[1, 2])  # door elkaar
        self.assertEqual(sim.cameras, [1])

    def test_auto_uit_wisselt_niet(self):
        sim = Simulatie()
        sim.r.actief = False
        sim.speel(8, praters=[1])
        self.assertEqual(sim.cameras, [])

    def test_handmatig_forceren(self):
        sim = Simulatie(shot_minimaal=4.0)
        sim.speel(6, praters=[1])
        sim.r.forceer(2, sim.t)
        sim.speel(3, praters=[1])
        self.assertEqual(sim.cameras, [1], "binnen shot_minimaal na handmatig niet terugwisselen")
        sim.speel(2, praters=[1])
        self.assertEqual(sim.cameras, [1, 1])

    def test_correctie_trekt_zachte_mic_gelijk(self):
        zonder = Simulatie()
        for _ in range(int(6 / STAP)):
            zonder.t += STAP
            self.assertIsNone(zonder.r.update(zonder.t, {1: STIL, 2: STIL, 3: STIL, 4: -48.0}))
        sim = Simulatie()
        # Mic van Gast 3 staat 10 dB te zacht: zonder correctie haalt hij de drempel niet.
        sim.sprekers[3].correctie_db = 10.0
        for _ in range(int(6 / STAP)):
            sim.t += STAP
            w = sim.r.update(sim.t, {1: STIL, 2: STIL, 3: STIL, 4: -48.0})
            if w:
                sim.wissels.append(w)
        self.assertEqual(sim.cameras, [1])


if __name__ == "__main__":
    unittest.main()
