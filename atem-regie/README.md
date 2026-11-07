# ATEM-regie

Een programma voor je Mac dat naar je microfoons luistert en de **ATEM Mini Pro** automatisch de juiste camera laat kiezen. Wie praat, komt in beeld. Praat iedereen door elkaar of is het stil, dan gaat het beeld naar het totaalshot. Bij een presentatie zet hij de spreker in een kader bij de dia's, of ernaast.

Je bedient alles met een paar toetsen en kunt op elk moment zelf ingrijpen.

## Hoe het in elkaar zit

```
4 mics → zenders → ontvanger → audio-interface → Mac
                                                  ├─ OBS (zoals nu)
                                                  └─ dit programma luistert mee
                                                        │
                                                        │ netwerkkabel
                                                        ▼
camera 1, 2, 3 + presentatie-laptop ──HDMI──▶  ATEM Mini Pro
```

Waarom via de Mac en niet direct in de ATEM? De ATEM Mini Pro heeft maar twee mic-ingangen. Via je audio-interface komen alle vier de mics los binnen, en dan kan het programma precies horen wie er praat. OBS en dit programma kunnen tegelijk naar dezelfde interface luisteren.

## Eenmalig instellen (ongeveer 20 minuten)

**1. Zet de ATEM aan het netwerk.** Steek een netwerkkabel in de ATEM en verbind die met je router. Je Mac mag via wifi op dezelfde router zitten. De USB-kabel blijft gewoon zitten voor het beeld.

**2. Zoek het IP-adres van de ATEM op.** Open *Blackmagic ATEM Setup* (die is meegekomen met ATEM Software Control). Kies je ATEM en kijk bij de netwerkinstellingen. Zet hem op *DHCP*, dan geeft je router hem zelf een adres. Noteer het IP-adres dat er staat.

**3. Zet deze map op je Mac.** Het makkelijkst gaat dat met Claude Code op je Mac. Zeg bijvoorbeeld: *"Haal github.com/jimklijn/Jim_1 op en open de map atem-regie in Finder."*

**4. Dubbelklik op `1 apparaten tonen.command`.**
- De eerste keer installeert hij wat nodig is. Vraagt je Mac om de *Command Line Tools*, kies dan *Installeer* en dubbelklik daarna opnieuw.
- Zegt macOS dat het bestand niet geopend kan worden? Klik dan met rechts op het bestand en kies *Open*.
- Je ziet nu je audio-interface staan, met het aantal kanalen. **Er moeten minstens 4 kanalen zijn.** Staan er maar 2, laat het me weten: dan stuurt de ontvanger of interface de mics samen door.

**5. Vul `instellingen.yaml` in.** Open het bestand met Teksteditor. Vul in:
- het IP-adres van de ATEM;
- (een deel van) de naam van je audio-interface;
- per spreker: op welk kanaal de mic binnenkomt en welke camera erbij hoort;
- welke camera het totaalshot is en op welke ingang de presentatie zit.

Bij elke regel staat uitleg.

**6. Dubbelklik op `2 geluidscheck.command`.** Volg het scherm: eerst is iedereen even stil, daarna praat iedereen om de beurt. Je krijgt een rapport met advies per mic. Het rapport controleert ook of elke mic op het goede kanaal binnenkomt, en stelt een drempel voor die hij meteen kan opslaan. Het rapport wordt bewaard in de map `rapporten`.

**7. Dubbelklik op `3 proefdraaien.command`.** De regie luistert naar je echte mics, maar laat de ATEM met rust. Praat wat met elkaar en kijk of hij de goede camera's kiest.

**8. Klaar? Dubbelklik op `4 regie starten.command`.** Nu stuurt hij de ATEM echt aan.

Wil je eerst zien hoe het werkt, zonder spullen aan te sluiten? Dubbelklik dan op `0 demo (zonder spullen).command`. Die verzint een gesprek.

De eerste keer vraagt macOS of Terminal je microfoon mag gebruiken. Klik op *Sta toe*, anders hoort het programma niets.

## Tijdens de show

| Toets | Wat het doet |
|---|---|
| `a` | Automatisch wisselen aan of uit |
| `1` `2` `3` `4` | Zelf een ingang kiezen. Automatisch gaat dan uit; druk `a` om het weer aan te zetten. |
| `t` | Naar het totaalshot |
| `c` | **Camera's**: alleen camera's in beeld (podcast) |
| `k` | **Presentatie + kader**: de presentatie groot, de spreker in een kader |
| `n` | **Naast elkaar**: de presentatie groot links, de spreker rechts in beeld |
| `p` | **Alleen presentatie** |
| `q` | Stoppen |

Ook in de presentatiemodi kiest de regie de spreker automatisch: het kader springt mee naar wie er praat.

Op het scherm zie je per mic een niveaumeter. Groen betekent "deze persoon praat en is in beeld", geel betekent "geluid, maar niet de spreker". Het streepje in de meter is de drempel.

## Het kader instellen

De ATEM Mini Pro heeft één beeld-in-beeld (*Upstream Key 1*, type DVE). Dit programma gebruikt die. Zet een logo daarom op een *Downstream Key*, niet op Upstream Key 1.

Wil je het kader ergens anders hebben?
1. Open ATEM Software Control, ga naar *Upstream Key 1 → DVE* en schuif het kader goed.
2. Neem de getallen bij *Position X*, *Position Y* en *Size* over in `instellingen.yaml` onder `layouts`.

Zie je het kader boven terwijl je het onder wilde, zet dan een minteken voor `y` (of haal het weg).

Bij *naast elkaar* staat de presentatie links en zie je de spreker rechts in het camerabeeld. Richt de camera's dan zo dat de mensen rechts in beeld zitten.

**Beperking van de Mini Pro:** er kunnen maximaal twee beelden tegelijk in beeld zijn, bijvoorbeeld de presentatie plus één camera. Alle camera's tegelijk in vakjes kan alleen de ATEM Mini Extreme. Wil je iedereen tegelijk zien, gebruik dan het totaalshot.

## Afstellen

Alles staat onder `regie:` in `instellingen.yaml`. Na een wijziging start je de regie opnieuw.

| Wat zie je? | Wat pas je aan? |
|---|---|
| Hij wisselt te zenuwachtig | `shot_minimaal` omhoog (5 of 6) en/of `praat_minimaal` omhoog (1,5) |
| Hij wisselt te laat | `praat_minimaal` omlaag (0,8) |
| Hij gaat te vaak naar het totaalshot als mensen door elkaar praten | `totaal_bij_door_elkaar` omhoog (3) of `dominant_db` omlaag (4) |
| Hij reageert op zuchten, schuiven of geroezemoes | `drempel_db` omhoog, bijvoorbeeld van -42 naar -38 |
| Hij ziet iemand niet praten | `drempel_db` omlaag, of geef die spreker een `correctie_db` |
| Geen afwisseling met het totaalshot bij lange verhalen | `afwisselen_na: 0` |
| Je hebt geen totaalcamera | `camera: totaal: 0` |

## Beter geluid

**1. Dubbel geluid of echo in OBS.** OBS krijgt het geluid twee keer binnen: via de ATEM (USB, met het geluid van de camera's) en via je audio-interface. Zet het ATEM-geluid in OBS op dempen, of zet in ATEM Software Control de camera-ingangen op *Off*.

**2. Geluid loopt voor op het beeld.** Beeld via de ATEM is iets later dan geluid via de interface. Ga in OBS naar *Geavanceerde audio-eigenschappen* en zet bij je interface een *sync-offset*. Begin bij 100 ms en doe een klaptest: klap in beeld, kijk de opname terug en verhoog de offset tot klap en geluid samenvallen.

**3. De mics zelf.** Doe de geluidscheck en volg het advies. In het kort:
- Praten moet groen worden in de meter en nooit rood.
- Alle mics ongeveer even hard.
- Zenders iets hoger op de borst, op dezelfde afstand van de mond.

**4. Op termijn: één laag in plaats van twee.** Stuur de mix van je audio-interface met een kabeltje naar mic-ingang 1 van de ATEM, en zet het camerageluid in de ATEM uit. Dan kan de ATEM Mini Pro zelf streamen en opnemen, met de knoppen ON AIR en REC, en heb je OBS niet meer nodig. Dit programma blijft gewoon naar de interface luisteren. Is het geluid dan te vroeg, dan stel je in ATEM Software Control bij de mic-ingang een vertraging in. Of dit kan, hangt af van je interface. Geef me het merk en type van je interface en ontvanger, dan zoek ik het precies voor je uit.

## Problemen oplossen

| Melding of probleem | Oplossing |
|---|---|
| *Geen verbinding met de ATEM* | Zit de netwerkkabel erin? Klopt het IP-adres (ATEM Setup)? Zitten Mac en ATEM op dezelfde router? |
| *Er komt helemaal geen geluid binnen* | Systeeminstellingen → Privacy en beveiliging → Microfoon → zet Terminal aan. Start daarna opnieuw. |
| *Audio-interface niet gevonden* | Dubbelklik `1 apparaten tonen.command` en neem de naam precies over. |
| *Geeft maar 2 kanalen door* | De ontvanger stuurt de mics samen door, of de interface heeft maar 2 ingangen. Laat het me weten. |
| Hij kiest steeds de verkeerde camera | Klopt `kanaal` en `camera` per spreker? De geluidscheck ziet ook omgewisselde mics. |
| Een mix-overgang haalt het kader weg | Zet in ATEM Software Control bij *Next Transition* alleen *BKGD* aan, niet *Key 1*. |
| Iets anders | Kijk in `regie.log`, of vraag Claude Code op je Mac: *"Lees regie.log en de rapporten in atem-regie en help me de regie af te stellen."* |

## Hoe het werkt

- Elke 50 milliseconden meet het programma hoe hard elke mic is.
- Iemand telt als "aan het praten" boven de drempel. Korte stiltes tussen woorden tellen mee als praten.
- Is één persoon duidelijk harder dan de rest, dan is dat de spreker. Het geluid dat een mic van de buurman opvangt, is veel zachter en telt dus niet mee.
- Pas als iemand een tijdje praat, komt hij in beeld. Een shot blijft altijd even staan. Zo geeft een kort "ja" of "hm" geen wissel.
- De ATEM wordt via het netwerk bestuurd met [PyATEMMax](https://github.com/clvLabs/PyATEMMax). De audio komt binnen via [sounddevice](https://python-sounddevice.readthedocs.io/).

| Bestand | Wat |
|---|---|
| `instellingen.yaml` | Jouw instellingen |
| `regie.py` | Het programma: scherm, toetsen, geluidscheck |
| `regisseur.py` | Het brein: beslist wie er in beeld komt |
| `geluidscheck.py` | Rekent het geluidsrapport uit |
| `apparaten.py` | Praat met de ATEM en de audio-interface (en de demo-versies) |
| `tests/` | Tests: `python3 -m unittest discover -s tests` |
