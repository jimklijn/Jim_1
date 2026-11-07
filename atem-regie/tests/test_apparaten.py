"""Tests voor het uitlezen van de audio-interface, met een nagebootste interface.
Draaien met:  python3 -m unittest discover -s tests   (numpy nodig; anders worden ze overgeslagen)"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


def nep_sounddevice(apparaten):
    """Een nagebootste 'sounddevice'-module met de opgegeven apparaten."""
    sd = types.ModuleType("sounddevice")
    sd.default = types.SimpleNamespace(device=[0, 0])
    sd.laatste_stream = None

    def query_devices(index=None):
        if index is None:
            return apparaten
        return apparaten[index]

    class InputStream:
        def __init__(self, **kw):
            self.kw = kw
            sd.laatste_stream = self

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

        def stuur(self, data):
            self.kw["callback"](data, len(data), None, None)

    sd.query_devices = query_devices
    sd.InputStream = InputStream
    return sd


APPARATEN = [
    {"name": "MacBook Pro-microfoon", "max_input_channels": 1, "default_samplerate": 48000.0},
    {"name": "Scarlett 18i8 USB", "max_input_channels": 8, "default_samplerate": 48000.0},
    {"name": "MacBook Pro-luidsprekers", "max_input_channels": 0, "default_samplerate": 48000.0},
]


@unittest.skipIf(np is None, "numpy is niet geïnstalleerd")
class TestNiveaumeter(unittest.TestCase):
    def setUp(self):
        self.sd = nep_sounddevice(APPARATEN)
        sys.modules["sounddevice"] = self.sd
        import apparaten

        self.apparaten = apparaten

    def tearDown(self):
        sys.modules.pop("sounddevice", None)

    def test_vindt_interface_op_deel_van_de_naam(self):
        m = self.apparaten.Niveaumeter("scarlett", 4)
        self.assertEqual(m.apparaat_naam, "Scarlett 18i8 USB")
        self.assertEqual(m.apparaat_index, 1)

    def test_onbekende_naam_geeft_lijst(self):
        with self.assertRaises(RuntimeError) as fout:
            self.apparaten.Niveaumeter("Focusrite Clarett", 4)
        self.assertIn("Scarlett 18i8 USB", str(fout.exception))
        self.assertNotIn("luidsprekers", str(fout.exception))

    def test_te_weinig_kanalen(self):
        with self.assertRaises(RuntimeError) as fout:
            self.apparaten.Niveaumeter("MacBook Pro-microfoon", 4)
        self.assertIn("maar 1 kanaal", str(fout.exception))

    def test_niveaus_per_kanaal(self):
        m = self.apparaten.Niveaumeter("Scarlett", 4)
        m.start()
        stream = self.sd.laatste_stream
        self.assertEqual(stream.kw["channels"], 4)
        self.assertEqual(stream.kw["blocksize"], 2400)  # 50 ms bij 48 kHz
        n = 2400
        t = np.arange(n) / 48000.0
        sinus = np.sin(2 * np.pi * 440 * t)
        data = np.zeros((n, 4), dtype=np.float32)
        data[:, 0] = 0.1 * sinus  # kanaal 1: -20 dBFS piek, -23 dB RMS
        data[:, 2] = 1.0 * sinus  # kanaal 3: vol uitgestuurd
        stream.stuur(data)
        meting = m.meting()
        self.assertAlmostEqual(meting.rms_db[0], -23.0, delta=0.2)
        self.assertAlmostEqual(meting.piek_db[0], -20.0, delta=0.2)
        self.assertEqual(meting.rms_db[1], -100.0)
        self.assertAlmostEqual(meting.piek_db[2], 0.0, delta=0.2)
        m.stop()


try:
    import PyATEMMax  # noqa: F401
except ImportError:  # pragma: no cover
    PyATEMMax = None


@unittest.skipIf(PyATEMMax is None, "PyATEMMax is niet geïnstalleerd")
class TestAtemOpdrachten(unittest.TestCase):
    """Vangt de netwerkpakketjes op in plaats van ze te versturen, en controleert ze."""

    def opdrachten(self, actie):
        import struct

        from apparaten import Atem

        atem = Atem("192.0.2.1", "mix")
        sw = atem.sw.switcher
        atem.sw.connected = sw.connected = True  # doen alsof er een ATEM is
        pakketten = []
        sw._sendCommand = lambda n: pakketten.append(bytes(sw._outBuf[:n]))
        actie(atem)
        uit = []
        for p in pakketten:
            body, i = p[12:], 0
            while i + 8 <= len(body):
                lengte = struct.unpack(">H", body[i:i + 2])[0]
                if lengte == 0:
                    break
                uit.append((body[i + 4:i + 8].decode(), body[i + 8:i + lengte]))
                i += lengte
        return uit

    def test_cut_en_mix(self):
        cmds = self.opdrachten(lambda a: (a.naar(2, "cut"), a.naar(3)))
        self.assertEqual([c for c, _ in cmds], ["CPgI", "CPvI", "DAut"])
        self.assertEqual(cmds[0][1], bytes([0, 0, 0, 2]))
        self.assertEqual(cmds[1][1], bytes([0, 0, 0, 3]))

    def test_kader_met_layout(self):
        from apparaten import Layout

        cmds = self.opdrachten(lambda a: a.kader(True, 1, Layout(0.3, 10.4, -5.5)))
        self.assertEqual([c for c, _ in cmds], ["CKeF", "CKTp", "CKDV", "CKDV", "CKDV", "CKDV", "CKOn"])
        self.assertEqual(cmds[0][1], bytes([0, 0, 0, 1]))  # bron = ingang 1
        self.assertEqual(cmds[1][1][3], 3)  # type = DVE
        waarden = [int.from_bytes(d[o:o + 4], "big", signed=True) for (_, d), o in zip(cmds[2:6], (8, 12, 16, 20))]
        self.assertEqual(waarden, [300, 300, 10400, -5500])
        self.assertEqual(cmds[6][1][:3], bytes([0, 0, 1]))  # aan

    def test_kader_uit(self):
        cmds = self.opdrachten(lambda a: a.kader(False))
        self.assertEqual(cmds, [("CKOn", bytes([0, 0, 0, 0]))])


if __name__ == "__main__":
    unittest.main()
