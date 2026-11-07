# Overdracht: ATEM-regie

Dit bestand is voor Claude Code op Jims Mac. Het vat samen wat er in de cloud-sessie is gebouwd en besproken, zodat je verder kunt waar die gebleven is.

## Jims opstelling

- **Switcher:** ATEM Mini Pro (4 HDMI-ingangen, 2 mic-ingangen, één upstream keyer met DVE).
- **Computer:** MacBook.
- **Beeld:** meestal 2, soms 3 camera's, plus een HDMI-ingang voor de presentatie-laptop.
- **Geluid:** 4 draadloze mics → ontvanger ("zendkastje") → audio-interface → MacBook. In OBS worden het beeld van de ATEM (via USB) en het geluid van de interface samengevoegd en gestreamd. Jim vindt dat twee lagen en vond de ATEM-software lastig, vooral het geluid.
- **Gebruik:** podcasts, en livestreams met presentatie. Bij een presentatie wil hij deels de presentatie en deels de mensen in beeld.
- **Onbekend:** merk en type van de audio-interface en van de ontvanger. Of de vier mics als vier losse kanalen op de Mac binnenkomen, is nog niet gecontroleerd.

## Wat er al is (deze map)

Een Python-programma dat via de audio-interface naar de vier mics luistert en de ATEM via het netwerk aanstuurt. Zie [README.md](README.md) voor de gebruiksuitleg.

- **`regisseur.py`:** beslist wie er in beeld komt.
  - De spreker die duidelijk het hardst praat, komt in beeld.
  - Iemand moet eerst even praten voordat er gewisseld wordt (`praat_minimaal`), en een shot blijft minstens een tijd staan (`shot_minimaal`).
  - Bij stilte of door elkaar praten gaat het beeld naar het totaalshot.
  - Bij een lange monoloog komt er af en toe een totaalshot tussen.
- **`regie.py`:** het scherm en de toetsen in Terminal, met drie opdrachten: `apparaten`, `geluidscheck` en `start` (met `--proef` en `--demo`). Er zijn vier modi:
  - `camera`: alleen camera's;
  - `kader`: presentatie groot, spreker in het kader;
  - `naast`: spreker in beeld, presentatie groot ernaast;
  - `presentatie`: alleen de presentatie.
- **`geluidscheck.py`:** een check in stappen.
  - Eerst is iedereen stil, dan praat iedereen om de beurt.
  - Per mic meet hij ruis, niveau, vervorming en overspraak.
  - Hij ziet omgewisselde en gekoppelde kanalen, en stelt een drempel voor.
- **`apparaten.py`:**
  - De koppeling met de ATEM (PyATEMMax) en met de interface (sounddevice).
  - Twee oefenversies: `ProefAtem` stuurt niets aan, `DemoBron` verzint een gesprek.
- **Dubbelklik-bestanden `0` t/m `4` (`.command`):** starten via `hulp/opstarten.sh`. Dat maakt de eerste keer zelf `.venv` aan.
- **Tests:** `python3 -m unittest discover -s tests` (28 tests). De ATEM-pakketten zijn byte voor byte nagekeken tegen het protocol (CPgI, CPvI/DAut, CKeF, CKTp, CKDV, CKOn).

**Nog niet getest met echte apparatuur.** Ook de richting van de DVE-positie Y is niet bevestigd: aangenomen is dat positief omhoog is. Controleer dat bij de eerste echte test.

## Volgende stappen (in deze volgorde)

1. **Eerste echte test.**
   - Zet de ATEM aan het netwerk en zoek het IP-adres op in Blackmagic ATEM Setup.
   - Vul `instellingen.yaml` in.
   - Draai `1 apparaten tonen.command`. Komen er 4 losse kanalen binnen?
   - Draai daarna `2 geluidscheck.command`, dan `3 proefdraaien.command`, dan `4 regie starten.command`.
   - Controleer of het kader rechtsonder staat.
2. **ATEM-instellingen nalopen.**
   - Jim bewaart zijn instellingen in ATEM Software Control met *File → Save As* (een XML-bestand).
   - Lees dat bestand. Leg uit wat er staat, stel verbeteringen voor en pas aan: camerageluid uit, mic-vertraging, kader, overgangen, namen van de ingangen.
   - Jim zet het terug met *File → Restore*. Bewaar altijd eerst een reservekopie.
3. **Meetprogramma voor beeld-geluid-synchronisatie bouwen** (nog niet gemaakt).
   - Jim speelt een filmpje af dat tegelijk flitst en piept, voor de camera, en neemt zo'n 15 seconden op.
   - Meet de flits in het beeld en de piep in het geluid (bijvoorbeeld met ffmpeg en numpy) en reken het verschil uit in milliseconden.
   - Geef de exacte waarde voor de sync-offset in OBS, of later voor de mic-vertraging in de ATEM (instelbaar sinds firmware 8.2.3).
   - Meet per camera, en nog een keer na 30 minuten om uitlopen te zien.
4. **Bediening kiezen.** Het tekstscherm werkt al. Voorgesteld is een venster met grote knoppen, of een Stream Deck. Jim heeft nog niet gekozen.
5. **Graphics maken.**
   - Een achtergrond of rand met logo, een logo in de hoek, en naambalken voor de gasten (PNG van 1920×1080 met transparantie).
   - Jim zet ze in de Media Pool en ze komen in beeld via een Downstream Key. Upstream Key 1 is bezet door het kader.
   - De regie kan een naambalk automatisch tonen bij de eerste keer in beeld, via `setMediaPlayerSourceStillIndex` en een DSK.
6. **Op termijn één laag in plaats van twee.**
   - De mix van de interface gaat naar mic-ingang 1 van de ATEM, en de ATEM streamt en neemt zelf op.
   - Dit hangt af van de interface, en het merk en type zijn nog onbekend.

## Openstaande vragen aan Jim

- Merk en type van de audio-interface en van de ontvanger.
- Venster met grote knoppen, of een Stream Deck?
- Het ATEM-instellingenbestand (XML).

## Goed om te weten

- Jim schrijft Nederlands en is geen programmeur. Leg dingen in gewone taal uit, kort, met concrete stappen.
- De ATEM Mini Pro kan maximaal twee bronnen tegelijk tonen (achtergrond plus één DVE). SuperSource heeft alleen de Extreme.
- PyATEMMax ondersteunt geen Fairlight-audiocommando's en geen uploads naar de Media Pool. Doe die via het instellingenbestand of ATEM Software Control, of stap over naar `atem-connection` (Node.js) als het echt via code moet.
- macOS moet Terminal toegang geven tot de microfoon, anders komt er alleen stilte binnen.
