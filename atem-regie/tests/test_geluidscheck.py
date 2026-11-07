"""Tests voor de analyse van de geluidscheck. Draaien met:  python3 -m unittest discover -s tests"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from geluidscheck import analyseer  # noqa: E402

MICS = [("Jim", 1), ("Gast 1", 2), ("Gast 2", 3), ("Gast 3", 4)]


def reeks(niveau, n=120, spreiding=3.0, zaad=0):
    r = random.Random(zaad)
    return [niveau + r.uniform(-spreiding, spreiding) for _ in range(n)]


def maak_check(spraak=None, ruis=-62.0, overspraak=-40.0, route=None, gekoppeld=(), piek_extra=9.0):
    """Bouw meetgegevens na. spraak = {kanaal: niveau als de eigenaar praat}.
    route = {naam: kanaal waar zijn stem echt binnenkomt} (voor omgewisselde mics)."""
    spraak = spraak or {}
    route = route or {}
    stil = {k: reeks(ruis, zaad=k) for _, k in MICS}
    beurten = {}
    for naam, eigen in MICS:
        echt = route.get(naam, eigen)
        metingen = {}
        for _, k in MICS:
            if k == echt or (echt in gekoppeld and k in gekoppeld):
                metingen[k] = reeks(spraak.get(echt, -18.0), zaad=10 * k + eigen)
            else:
                metingen[k] = reeks(overspraak, zaad=20 * k + eigen)
        beurten[naam] = metingen
    piek = {k: [v + piek_extra for b in beurten.values() for v in b[k]] for _, k in MICS}
    return stil, beurten, piek


class TestGeluidscheck(unittest.TestCase):
    def test_alles_goed(self):
        rapport = analyseer(MICS, *maak_check())
        self.assertEqual([m.oordeel for m in rapport.mics], ["goed"] * 4)
        self.assertEqual(rapport.algemeen, [])
        self.assertTrue(-45 <= rapport.drempel_advies <= -35, rapport.drempel_advies)

    def test_omgewisselde_mics(self):
        rapport = analyseer(MICS, *maak_check(route={"Jim": 3, "Gast 2": 1}))
        tekst = " ".join(rapport.algemeen)
        self.assertIn("Toen Jim praatte, was kanaal 3 het hardst", tekst)
        self.assertIn("omgewisseld", tekst)

    def test_gekoppelde_kanalen(self):
        rapport = analyseer(MICS, *maak_check(gekoppeld=(1, 2)))
        self.assertTrue(any("gekoppeld" in a for a in rapport.algemeen), rapport.algemeen)

    def test_mic_uit(self):
        stil, beurten, piek = maak_check()
        beurten["Gast 3"][4] = reeks(-61.0)
        for naam in beurten:
            beurten[naam][4] = reeks(-61.0)
        rapport = analyseer(MICS, stil, beurten, piek)
        gast3 = rapport.mics[3]
        self.assertEqual(gast3.oordeel, "uit")
        self.assertIn("kanaal 4", gast3.adviezen[0])

    def test_vervorming(self):
        stil, beurten, piek = maak_check()
        piek[2] = piek[2] + [0.0, -0.3]
        rapport = analyseer(MICS, stil, beurten, piek)
        self.assertEqual(rapport.mics[1].oordeel, "hard")

    def test_te_zacht_en_ongelijk(self):
        rapport = analyseer(MICS, *maak_check(spraak={4: -36.0}))
        self.assertEqual(rapport.mics[3].oordeel, "zacht")
        self.assertTrue(any("ongelijk" in a for a in rapport.algemeen))
        self.assertIn("Gast 3", rapport.correcties)
        self.assertGreater(rapport.correcties["Gast 3"], 0)

    def test_rapport_is_leesbaar(self):
        tekst = analyseer(MICS, *maak_check()).als_tekst()
        self.assertIn("Aanbevolen drempel", tekst)
        self.assertIn("Jim", tekst)


if __name__ == "__main__":
    unittest.main()
