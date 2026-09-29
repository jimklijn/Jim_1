#!/usr/bin/env python3
"""Bureaublad opruimen voor macOS: eerst een plan, jij kijkt mee, dan pas uitvoeren.

  1. python3 opruimen.py scan [--server /Volumes/<naam>/<map>]
       Kijkt naar je bureaublad en schrijft opruimplan.txt. Verandert niets.
  2. Open opruimplan.txt (TextEdit) en pas de eerste kolom aan waar je het er niet mee eens bent.
  3. python3 opruimen.py toepassen
       Laat een samenvatting zien, vraagt om 'ja' en voert het plan uit.
  4. python3 opruimen.py terugdraaien
       Zet het sorteren van de laatste keer terug.

Acties in de eerste kolom van het plan:
  houden          laten staan
  weg             naar de Prullenbak (terug te halen tot je die leegt)
  server          naar de videoserver kopiëren, controleren, origineel naar de Prullenbak
  sorteer:<Map>   verplaatsen naar <doelmap>/<Map>

Er wordt alleen iets gedaan met wat in het plan staat. Niets wordt overschreven of definitief
gewist. Alleen de standaardbibliotheek, Python 3.8 of nieuwer.
"""

import argparse
import glob
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

STANDAARD_PLAN = "opruimplan.txt"
DOELMAP_NAAM = "Opgeruimd"

VIDEO = {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv", ".mts", ".m2ts", ".mpg", ".mpeg",
         ".wmv", ".webm", ".r3d", ".braw"}
CATEGORIEEN = {
    "Video": VIDEO,
    "Audio": {".wav", ".mp3", ".aif", ".aiff", ".m4a", ".aac", ".flac", ".ogg"},
    "Afbeeldingen": {".jpg", ".jpeg", ".png", ".gif", ".heic", ".tif", ".tiff", ".webp", ".bmp",
                     ".svg", ".raw", ".cr2", ".cr3", ".arw", ".nef", ".dng"},
    "Documenten": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pages", ".numbers",
                   ".key", ".txt", ".rtf", ".md", ".csv", ".odt", ".ods", ".odp"},
    "Archieven": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"},
    "Lettertypen": {".otf", ".ttf", ".ttc", ".woff", ".woff2"},
    "Scripts": {".jsx", ".jsxbin", ".js", ".py", ".sh", ".command", ".applescript", ".scpt"},
}
# Projecten verwijzen naar media met een vast pad: die laten we staan.
PROJECTEN = {".prproj", ".aep", ".aepx", ".aet", ".psd", ".psb", ".ai", ".indd", ".idml",
             ".sketch", ".fig", ".drp", ".fcpxml", ".mogrt"}
PAKKETTEN = {".app", ".photoslibrary", ".fcpbundle", ".imovielibrary", ".logicx", ".band",
             ".sparsebundle", ".tvlibrary", ".musiclibrary"}
INSTALLATIE = {".dmg", ".pkg", ".mpkg"}
TIJDELIJK = {".tmp", ".temp"}
HALVE_DOWNLOAD = {".crdownload", ".part", ".partial", ".download"}
SCHERMFOTO = re.compile(r"^(Schermafbeelding|Schermopname|Screenshot|Screen Shot|Screen Recording)"
                        r"\s+\d{4}-\d{2}-\d{2}")
KOPIE = re.compile(r"( \(\d+\)| kopie( \d+)?| copy( \d+)?)(\.[^.]*)?$", re.I)


@dataclass
class Item:
    naam: str
    actie: str  # houden | weg | server | sorteer:<Map>
    reden: str = ""
    grootte: int = 0
    is_map: bool = False


def fout(tekst):
    print("Fout: " + tekst, file=sys.stderr)
    sys.exit(1)


def mens(n):
    n = float(n)
    for eenheid in ("B", "KB", "MB", "GB"):
        if n < 1000:
            return "%d B" % n if eenheid == "B" else ("%.1f %s" % (n, eenheid)).replace(".", ",")
        n /= 1000
    return ("%.1f TB" % n).replace(".", ",")


def uniek_pad(pad):
    """Geeft pad terug, of 'pad (2)', 'pad (3)'... zodat er nooit iets wordt overschreven."""
    if not os.path.lexists(pad):
        return pad
    stam, ext = os.path.splitext(pad)
    n = 2
    while os.path.lexists("%s (%d)%s" % (stam, n, ext)):
        n += 1
    return "%s (%d)%s" % (stam, n, ext)


def sha256(pad):
    h = hashlib.sha256()
    with open(pad, "rb") as f:
        for blok in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blok)
    return h.hexdigest()


def meet_map(pad):
    """(bytes, bytes video, aantal bestanden) van een map, zonder symlinks te volgen."""
    totaal = video = aantal = 0
    for wortel, _mappen, bestanden in os.walk(pad):
        for b in bestanden:
            if b == ".DS_Store":
                continue
            try:
                grootte = os.lstat(os.path.join(wortel, b)).st_size
            except OSError:
                continue
            aantal += 1
            totaal += grootte
            if os.path.splitext(b)[1].lower() in VIDEO:
                video += grootte
    return totaal, video, aantal


def grootte_van(pad):
    st = os.lstat(pad)
    return meet_map(pad)[0] if stat.S_ISDIR(st.st_mode) else st.st_size


# ---------------------------------------------------------------- plan maken

def beoordeel(bureaublad, naam, server, oud_dagen, nu):
    pad = os.path.join(bureaublad, naam)
    st = os.lstat(pad)
    ext = os.path.splitext(naam)[1].lower()
    dagen = (nu - st.st_mtime) / 86400

    if stat.S_ISLNK(st.st_mode):
        return Item(naam, "houden", "snelkoppeling (symlink)")

    if stat.S_ISDIR(st.st_mode):
        totaal, video, aantal = meet_map(pad)
        if ext in PAKKETTEN:
            return Item(naam, "houden", "programma of bibliotheek", totaal, True)
        if ext in HALVE_DOWNLOAD:
            if dagen > 1:
                return Item(naam, "weg", "onvolledige download", totaal, True)
            return Item(naam, "houden", "download nog bezig?", totaal, True)
        if aantal == 0:
            return Item(naam, "weg", "lege map", is_map=True)
        reden = "map met %d bestand%s" % (aantal, "" if aantal == 1 else "en")
        if totaal and video >= 0.8 * totaal:
            reden += ", %d%% video" % round(100 * video / totaal)
        return Item(naam, "houden", reden, totaal, True)

    if not stat.S_ISREG(st.st_mode):
        return Item(naam, "houden", "bijzonder bestandstype")

    grootte = st.st_size
    if grootte == 0:
        return Item(naam, "weg", "leeg bestand")
    if naam.startswith("~$") or ext in TIJDELIJK:
        return Item(naam, "weg", "tijdelijk bestand", grootte)
    if ext in HALVE_DOWNLOAD:
        if dagen > 1:
            return Item(naam, "weg", "onvolledige download", grootte)
        return Item(naam, "houden", "download nog bezig?", grootte)
    if ext in INSTALLATIE:
        return Item(naam, "weg", "installatiebestand (staat meestal al geïnstalleerd)", grootte)
    if ext == ".zip" and os.path.isdir(os.path.join(bureaublad, naam[:-4])):
        return Item(naam, "weg", "al uitgepakt (de map staat ernaast)", grootte)
    if SCHERMFOTO.match(naam):
        if dagen > oud_dagen:
            return Item(naam, "weg", "schermafbeelding ouder dan %d dagen" % oud_dagen, grootte)
        return Item(naam, "sorteer:Schermafbeeldingen", "schermafbeelding", grootte)
    if ext in PROJECTEN:
        return Item(naam, "houden", "projectbestand, laat ik staan", grootte)
    for categorie, extensies in CATEGORIEEN.items():
        if ext in extensies:
            if categorie == "Video" and server:
                return Item(naam, "server", "video", grootte)
            return Item(naam, "sorteer:" + categorie, ext, grootte)
    return Item(naam, "sorteer:Overig", ext or "geen extensie", grootte)


def markeer_dubbelen(bureaublad, items):
    """Bestanden met exact dezelfde inhoud: één blijft er, de rest gaat naar de Prullenbak."""
    per_grootte = defaultdict(list)
    for i in items:
        if not i.is_map and i.grootte > 0 and i.actie not in ("weg", "houden"):
            per_grootte[i.grootte].append(i)
    for groep in per_grootte.values():
        if len(groep) < 2:
            continue
        per_hash = defaultdict(list)
        for i in groep:
            try:
                per_hash[sha256(os.path.join(bureaublad, i.naam))].append(i)
            except OSError:
                continue
        for gelijk in per_hash.values():
            gelijk.sort(key=lambda i: (bool(KOPIE.search(i.naam)), len(i.naam), i.naam.lower()))
            for i in gelijk[1:]:
                i.actie, i.reden = "weg", "dubbel van '%s'" % gelijk[0].naam


def waarschuwingen(items):
    projecten = [i.naam for i in items if os.path.splitext(i.naam)[1].lower() in PROJECTEN]
    verplaatst = [i for i in items if i.actie == "server" or i.actie in
                  ("sorteer:Video", "sorteer:Audio", "sorteer:Afbeeldingen")]
    if projecten and verplaatst:
        return ["LET OP: er staan projectbestanden op je bureaublad (%s). Media die daarin gebruikt "
                "worden en hier worden verplaatst, moet je daarna opnieuw koppelen. "
                "Zet die bestanden op 'houden' als een project nog loopt." % ", ".join(projecten[:5])]
    return []


def schrijf_plan(planpad, bureaublad, doel, server, items, meldingen):
    def sleutel(i):
        return ({"server": 0, "weg": 2, "houden": 3}.get(i.actie, 1), i.actie, i.naam.lower())

    regels = [
        "# Opruimplan van %s" % time.strftime("%Y-%m-%d %H:%M"),
        "# Pas de EERSTE kolom aan als je iets anders wilt: houden | weg | server | sorteer:<Mapnaam>",
        "# Regels met # worden genegeerd. 'weg' = naar de Prullenbak. Alleen wat hier staat wordt aangeraakt.",
    ] + ["# " + m for m in meldingen] + [
        "@bureaublad\t" + bureaublad,
        "@doel\t" + doel,
    ]
    if server:
        regels.append("@server\t" + server)
    regels.append("")
    for i in sorted(items, key=sleutel):
        regels.append("\t".join([i.actie, i.naam, mens(i.grootte) if i.grootte else "", i.reden]))
    with open(planpad, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write("\n".join(regels) + "\n")


def toon_samenvatting(items, doel, server_map, met_houden):
    groepen = defaultdict(list)
    for i in items:
        groepen[i.actie.split(":")[0]].append(i)
    kopjes = [("server", "NAAR DE VIDEOSERVER"), ("sorteer", "SORTEREN"),
              ("weg", "NAAR DE PRULLENBAK (terug te halen)")]
    if met_houden:
        kopjes.append(("houden", "LATEN STAAN"))
    for sleutel, kop in kopjes:
        groep = groepen.get(sleutel)
        if not groep:
            continue
        print("\n%s: %d items, %s" % (kop, len(groep), mens(sum(i.grootte for i in groep))))
        if sleutel == "server":
            print("  naar %s" % server_map)
        if sleutel == "sorteer":
            per_map = defaultdict(list)
            for i in groep:
                per_map[i.actie.split(":", 1)[1]].append(i.naam)
            for map_, namen in sorted(per_map.items()):
                print("  %s/%s (%d): %s%s" % (os.path.basename(doel), map_, len(namen),
                                              ", ".join(namen[:4]), ", ..." if len(namen) > 4 else ""))
            continue
        for i in groep[:25]:
            print("  - %s (%s)%s" % (i.naam, mens(i.grootte), "  [%s]" % i.reden if i.reden else ""))
        if len(groep) > 25:
            print("  ... en nog %d (zie het plan)" % (len(groep) - 25))


def server_submap(server):
    return os.path.join(server, "Bureaublad opgeruimd " + time.strftime("%Y-%m-%d"))


def server_ontbreekt(server):
    tekst = ("Ik kan de map %s niet vinden.\nIs de videoserver verbonden (Finder > Ga > Verbind met "
             "server, ⌘K) en klopt het pad? Verbonden schijven staan onder /Volumes." % server)
    try:
        tekst += "\nNu verbonden: " + ", ".join(sorted(os.listdir("/Volumes")))
    except OSError:
        pass
    return tekst


def cmd_scan(args):
    bureaublad = os.path.abspath(os.path.expanduser(args.bureaublad))
    doel = (os.path.abspath(os.path.expanduser(args.doel)) if args.doel
            else os.path.join(bureaublad, DOELMAP_NAAM))
    server = None
    if args.server:
        server = os.path.abspath(os.path.expanduser(args.server))
        if not os.path.isdir(server):
            fout(server_ontbreekt(server))
    if not os.path.isdir(bureaublad):
        fout("De map %s bestaat niet." % bureaublad)
    try:
        namen = os.listdir(bureaublad)
    except OSError as e:
        fout("Ik kan %s niet lezen (%s).\nGeef Terminal toegang onder Systeeminstellingen > Privacy "
             "en beveiliging > Bestanden en mappen (of Volledige schijftoegang) en probeer opnieuw."
             % (bureaublad, e))

    nu = time.time()
    items, overgeslagen = [], []
    for naam in sorted(namen, key=str.lower):
        if naam.startswith("."):
            continue  # verborgen bestanden (.DS_Store e.d.) blijven met rust
        if os.path.dirname(doel) == bureaublad and naam == os.path.basename(doel):
            continue  # hier komt het gesorteerde spul terecht
        if any(ord(c) < 32 for c in naam):
            if naam != "Icon\r":
                overgeslagen.append(naam)
            continue
        try:
            items.append(beoordeel(bureaublad, naam, server, args.oud, nu))
        except OSError as e:
            overgeslagen.append("%s (%s)" % (naam, e))

    if not items:
        print("Je bureaublad (%s) is al leeg." % bureaublad)
        return
    markeer_dubbelen(bureaublad, items)
    meldingen = waarschuwingen(items)
    schrijf_plan(args.plan, bureaublad, doel, server, items, meldingen)

    print("Bureaublad: %s (%d items)" % (bureaublad, len(items)))
    toon_samenvatting(items, doel, server_submap(server) if server else None, met_houden=True)
    for m in meldingen:
        print("\n" + m)
    for naam in overgeslagen:
        print("Overgeslagen (rare naam of niet leesbaar): %r" % naam)
    videos = [i for i in items if i.actie == "sorteer:Video"]
    if videos:
        print("\nTip: %d %s (%s) staan nu op 'sorteer:Video'. Verbind de videoserver en draai "
              "scan opnieuw met --server /Volumes/<naam>/<map> om ze daarheen te laten gaan."
              % (len(videos), "video" if len(videos) == 1 else "video's",
                 mens(sum(i.grootte for i in videos))))
    print("\nPlan geschreven naar %s. Er is nog niets veranderd." % os.path.abspath(args.plan))
    print("Bekijk en pas aan met:  open %s" % args.plan)
    print("Uitvoeren met:          python3 %s toepassen" % os.path.basename(sys.argv[0]))


# ---------------------------------------------------------------- plan uitvoeren

def lees_plan(planpad):
    if not os.path.isfile(planpad):
        fout("Geen plan gevonden op %s. Draai eerst 'scan'." % planpad)
    instellingen, taken, problemen = {}, [], []
    with open(planpad, encoding="utf-8", errors="surrogateescape") as f:
        for nr, regel in enumerate(f, 1):
            regel = regel.rstrip("\r\n")
            if not regel.strip() or regel.lstrip().startswith("#"):
                continue
            delen = regel.split("\t")
            if delen[0].startswith("@"):
                instellingen[delen[0][1:].strip()] = delen[1] if len(delen) > 1 else ""
                continue
            if len(delen) < 2:
                problemen.append("regel %d: verwacht 'actie', een tab en dan de naam" % nr)
                continue
            soort, _, map_ = delen[0].strip().partition(":")
            soort, map_, naam = soort.strip().lower(), map_.strip(), delen[1]
            if soort not in ("houden", "weg", "server", "sorteer"):
                problemen.append("regel %d: onbekende actie '%s'" % (nr, delen[0].strip()))
            elif soort == "sorteer" and (not map_ or "/" in map_ or map_.startswith(".")):
                problemen.append("regel %d: 'sorteer:' heeft een geldige mapnaam nodig" % nr)
            elif not naam or "/" in naam or naam.startswith("."):
                problemen.append("regel %d: ongeldige naam '%s'" % (nr, naam))
            else:
                taken.append(Item(naam, soort + (":" + map_ if soort == "sorteer" else "")))
    if problemen:
        fout("Het plan bevat fouten, er is niets gedaan:\n  " + "\n  ".join(problemen))
    return instellingen, taken


def prullenbak(pad):
    """Zet pad in de Prullenbak (via Finder, zodat 'Zet terug' werkt). Geeft een label terug."""
    reden = "geen macOS"
    if sys.platform == "darwin":
        script = ('on run argv\n'
                  '  set p to item 1 of argv\n'
                  '  tell application "Finder" to delete (POSIX file p)\n'
                  'end run')
        try:
            r = subprocess.run(["osascript", "-e", script, pad], capture_output=True, text=True,
                               timeout=120)
            if r.returncode == 0 and not os.path.lexists(pad):
                return "Prullenbak"
            reden = (r.stderr or "").strip() or "Finder deed het niet"
        except (OSError, subprocess.TimeoutExpired) as e:
            reden = str(e)
    trash = os.path.join(os.path.expanduser("~"), ".Trash")
    try:
        os.makedirs(trash, exist_ok=True)
        shutil.move(pad, uniek_pad(os.path.join(trash, os.path.basename(pad))))
        return "Prullenbak (~/.Trash)"
    except OSError as e:
        raise RuntimeError("kon niet naar de Prullenbak (%s; %s). Geef Terminal toestemming onder "
                           "Systeeminstellingen > Privacy en beveiliging > Automatisering > Finder"
                           % (reden, e))


def kopieer_boom(bron, doel):
    # Alleen inhoud en datum: Finder-labels en tags gaan niet mee (netwerkschijven weigeren metadata nogal eens).
    if os.path.islink(bron):
        os.symlink(os.readlink(bron), doel)
    elif os.path.isdir(bron):
        os.mkdir(doel)
        for naam in os.listdir(bron):
            kopieer_boom(os.path.join(bron, naam), os.path.join(doel, naam))
    else:
        shutil.copyfile(bron, doel)
        try:
            st = os.stat(bron)
            os.utime(doel, (st.st_atime, st.st_mtime))
        except OSError:
            pass  # datum meenemen is mooi meegenomen, niet essentieel (netwerkschijven weigeren dit soms)


def bestandsgroottes(pad):
    """{relatief pad: grootte} van alle gewone bestanden onder pad, om een kopie mee te controleren."""
    if os.path.isfile(pad) and not os.path.islink(pad):
        return {"": os.path.getsize(pad)}
    res = {}
    for wortel, _mappen, bestanden in os.walk(pad):
        for b in bestanden:
            p = os.path.join(wortel, b)
            if not os.path.islink(p):
                sleutel = unicodedata.normalize("NFC", os.path.relpath(p, pad))
                res[sleutel] = os.path.getsize(p)
    return res


def naar_server(pad, submap):
    os.makedirs(submap, exist_ok=True)
    doel = uniek_pad(os.path.join(submap, os.path.basename(pad)))
    try:
        kopieer_boom(pad, doel)
        if bestandsgroottes(pad) != bestandsgroottes(doel):
            raise RuntimeError("de kopie op de server wijkt af van het origineel")
    except BaseException:
        try:  # halve kopie die we zelf net maakten opruimen, nooit het origineel
            if os.path.isdir(doel) and not os.path.islink(doel):
                shutil.rmtree(doel)
            elif os.path.lexists(doel):
                os.remove(doel)
        except OSError:
            pass
        raise
    return doel


def verplaats(pad, doelmap):
    os.makedirs(doelmap, exist_ok=True)
    doel = uniek_pad(os.path.join(doelmap, os.path.basename(pad)))
    shutil.move(pad, doel)
    return doel


def cmd_toepassen(args):
    instellingen, taken = lees_plan(args.plan)
    bureaublad = instellingen.get("bureaublad") or os.path.expanduser("~/Desktop")
    doel = instellingen.get("doel") or os.path.join(bureaublad, DOELMAP_NAAM)
    server = instellingen.get("server") or None

    te_doen = []
    for taak in taken:
        if taak.actie == "houden":
            continue
        pad = os.path.join(bureaublad, taak.naam)
        if not os.path.lexists(pad):
            print("Overgeslagen (staat er niet meer): %s" % taak.naam)
            continue
        taak.grootte = grootte_van(pad)
        te_doen.append(taak)
    if not te_doen:
        print("Niets te doen.")
        return
    if any(t.actie == "server" for t in te_doen):
        if not server:
            fout("Het plan heeft 'server'-acties maar geen @server-regel. Draai scan opnieuw met --server.")
        if not os.path.isdir(server):
            fout(server_ontbreekt(server))

    print("Bureaublad: %s" % bureaublad)
    submap = server_submap(server) if server else None
    toon_samenvatting(te_doen, doel, submap, met_houden=False)
    if args.droog:
        print("\n(--droog: er is niets uitgevoerd)")
        return
    if not args.ja:
        try:
            antwoord = input("\nTyp 'ja' om dit uit te voeren (iets anders = stoppen): ").strip().lower()
        except EOFError:
            antwoord = ""
        if antwoord not in ("ja", "j", "yes", "y"):
            print("Gestopt, er is niets veranderd.")
            return

    logpad = "opruimlog-%s.tsv" % time.strftime("%Y%m%d-%H%M%S")
    log = open(logpad, "a", encoding="utf-8", errors="surrogateescape", buffering=1)
    gelukt, mislukt, server_klaar = 0, [], 0
    volgorde = {"sorteer": 0, "weg": 1, "server": 2}
    te_doen.sort(key=lambda t: volgorde[t.actie.split(":")[0]])
    for n, taak in enumerate(te_doen, 1):
        soort = taak.actie.split(":")[0]
        pad = os.path.join(bureaublad, taak.naam)
        try:
            if soort == "sorteer":
                naar = verplaats(pad, os.path.join(doel, taak.actie.split(":", 1)[1]))
            elif soort == "weg":
                naar = prullenbak(pad)
            else:
                print("[%d/%d] %s (%s) naar de server kopiëren...  even geduld" %
                      (n, len(te_doen), taak.naam, mens(taak.grootte)), flush=True)
                naar = naar_server(pad, submap)
                try:
                    prullenbak(pad)
                except Exception as e:
                    raise RuntimeError("de kopie staat veilig op de server (%s), maar het origineel "
                                       "staat nog op je bureaublad: %s" % (naar, e))
            log.write("%s\t%s\t%s\n" % (soort, pad, naar))
            gelukt += 1
            if soort == "server":
                server_klaar += 1
        except Exception as e:
            mislukt.append("%s: %s" % (taak.naam, e))
    log.close()

    print("\nKlaar: %d gelukt, %d mislukt. Logboek: %s" % (gelukt, len(mislukt), os.path.abspath(logpad)))
    for m in mislukt:
        print("  MISLUKT  " + m)
    if server_klaar:
        print("Controleer op de server of alles er staat voordat je de Prullenbak leegt: de originelen "
              "liggen daar nog.")
    print("Sorteren ongedaan maken:  python3 %s terugdraaien" % os.path.basename(sys.argv[0]))
    if mislukt:
        sys.exit(1)


def cmd_terugdraaien(args):
    logpad = args.logbestand
    if not logpad:
        logs = sorted(glob.glob("opruimlog-*.tsv"))
        if not logs:
            fout("Geen opruimlog-*.tsv gevonden in deze map.")
        logpad = logs[-1]
    with open(logpad, encoding="utf-8", errors="surrogateescape") as f:
        regels = [r.rstrip("\r\n").split("\t") for r in f if r.strip()]

    teruggezet, mappen = 0, set()
    for soort, van, naar in reversed(regels):
        if soort != "sorteer":
            continue
        if os.path.lexists(naar) and not os.path.lexists(van):
            shutil.move(naar, van)
            mappen.add(os.path.dirname(naar))
            teruggezet += 1
        else:
            print("Overgeslagen (al verplaatst of de plek is bezet): %s" % os.path.basename(van))
    for map_ in sorted(mappen, key=len, reverse=True):
        for m in (map_, os.path.dirname(map_)):
            try:
                os.rmdir(m)  # lukt alleen als de map leeg is
            except OSError:
                pass
    print("%d items teruggezet naar het bureaublad (logboek: %s)." % (teruggezet, logpad))
    weg = [r for r in regels if r[0] == "weg"]
    server = [r for r in regels if r[0] == "server"]
    if weg:
        print("%d items staan in de Prullenbak: rechtermuisklik > 'Zet terug' (als je hem niet leegde)."
              % len(weg))
    for _soort, van, naar in server:
        print("Op de server: %s  (origineel zat op %s)" % (naar, van))


def main():
    for stroom in (sys.stdout, sys.stderr):
        if hasattr(stroom, "reconfigure"):
            stroom.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description="Bureaublad opruimen: eerst een plan, dan pas uitvoeren.")
    sub = ap.add_subparsers(dest="commando", required=True)

    scan = sub.add_parser("scan", help="maak een plan (verandert niets)")
    scan.add_argument("--bureaublad", default="~/Desktop", help="map om op te ruimen (standaard ~/Desktop)")
    scan.add_argument("--server", help="videoserver-map, bijv. /Volumes/Video/Jim; zonder dit blijven video's lokaal")
    scan.add_argument("--doel", help="waar gesorteerde bestanden heen gaan (standaard <bureaublad>/Opgeruimd)")
    scan.add_argument("--oud", type=int, default=60, metavar="DAGEN",
                      help="schermafbeeldingen ouder dan dit gaan naar de Prullenbak (standaard 60)")
    scan.add_argument("--plan", default=STANDAARD_PLAN)
    scan.set_defaults(func=cmd_scan)

    toep = sub.add_parser("toepassen", help="voer het plan uit")
    toep.add_argument("--plan", default=STANDAARD_PLAN)
    toep.add_argument("--droog", action="store_true", help="alleen de samenvatting laten zien")
    toep.add_argument("--ja", action="store_true", help="niet om bevestiging vragen")
    toep.set_defaults(func=cmd_toepassen)

    terug = sub.add_parser("terugdraaien", help="zet het sorteren van een eerdere keer terug")
    terug.add_argument("logbestand", nargs="?", help="standaard: het nieuwste opruimlog-*.tsv in deze map")
    terug.set_defaults(func=cmd_terugdraaien)

    args = ap.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nGestopt. Wat al gedaan is staat in het logbestand.")
        sys.exit(130)


if __name__ == "__main__":
    main()
