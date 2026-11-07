# Jims Regiekamer

Een persoonlijk dashboard, gemaakt voor en door Jim: je dag, je taken, je mail en je notities op één scherm.

**Openen:** https://claude.ai/artifact/WgvHxkZQg9GAHeHQCGjc4o (privé, alleen jij kunt het openen)

De bron staat in [`dashboard/regiekamer.html`](dashboard/regiekamer.html).

## Wat erop staat

Het ontwerp is **Widgets**: kleurrijke tegels in een bento-raster, gekozen door Jim uit vier richtingen. De andere drie staan in [`dashboard/ontwerpen/`](dashboard/ontwerpen/).

| Onderdeel | Wat het doet |
|---|---|
| **Hierna** | De grote tegel bovenaan: aftellen tot je volgende afspraak, met plaats, duur en wanneer je moet vertrekken. De tegel kleurt mee (kobalt werk, jade privé, framboos mail) en toont een mini-tijdlijn van je dag. |
| **Voortgang** | Ringen voor je werkdag, werktaken en privétaken, plus de taak die te laat is, met een afvinkknop. |
| **Wacht op jou** | Hoeveel mails op antwoord wachten en wie het langst wacht. Klik en je springt naar die mail. |
| **Licht vandaag** | De echte tijden voor zonsopkomst, gouden uur en zonsondergang in Amsterdam, met een zonneboog. Handig voor dronebeelden. De achtergrond van de hele pagina kleurt mee met het licht buiten. |
| **Opdrachtregel** | Typ een taak en druk op Enter. Of klik op *Laat Claude inplannen*: Claude haalt taken en afspraken uit gewone taal ("morgen 10:00 tandarts, vrijdag hotelvideo's opleveren"). |
| **Tijdlijn** | Je dag met een spoor voor afspraken en een spoor voor tijdblokken, de werktijd, het gouden uur en een rode lijn voor nu. *Plan mijn dag* laat Claude je taken tussen je afspraken inplannen. Je ziet eerst een voorstel, ook als leesbaar lijstje, en neemt het met één klik over. |
| **Taken** | Vandaag, komende week, later en klaar, te filteren op werk of privé. Wat te laat is valt op. Met één klik schuif je een taak naar morgen. |
| **Mail** | Live uit Gmail. *Wacht op jou* toont persoonlijke mail waarop je nog niet hebt gereageerd. *Sorteer met Claude* verdeelt je inbox in antwoorden, actie, lezen en kan weg. Van elke mail kun je een taak maken, of Claude een concept-antwoord laten schrijven dat als concept in Gmail komt. Er wordt nooit iets verstuurd. |
| **Notities** | Snel iets vastleggen, vastzetten of er een taak van maken. Daaronder je recente bestanden uit Google Drive. |
| **Draaiboek** | De hele week, met de zonsondergang per dag. Met *Verdeel taken over de week* zet Claude losse taken op een dag waar ruimte is. |

## Hoe het werkt

- Het is een pagina op claude.ai. Er is geen server en er zijn geen API-sleutels nodig.
- Mail en Drive komen binnen via je eigen koppelingen (Gmail, Google Drive). De pagina vraagt de eerste keer toestemming.
- Taken, afspraken en notities worden bewaard in de eigen opslag van de pagina, onder jouw account en afgeschermd voor anderen. Deel je de link toch, dan ziet iemand anders zijn eigen, lege dashboard.
- De Claude-knoppen gebruiken je eigen Claude-account en werken pas als je erop klikt.

## Nog te doen

- **Agenda:** Google Agenda is nog niet gekoppeld. Voor nu voeg je afspraken zelf toe (klik op het afsprakenspoor). Koppel Google Agenda in claude.ai via *Instellingen → Connectors*, dan zetten we je echte afspraken live op de tijdlijn. Staat je werkagenda in Outlook, rond dan ook de Microsoft 365-koppeling af.
- Mail komt alleen uit Gmail (klijnjim@gmail.com). Je Hotmail- en werkmail volgen zodra Microsoft 365 gekoppeld is.

## Bestaat dit al op GitHub?

Deels. Er zijn open-source dashboards, maar die draai je zelf op een server of via Docker, en je moet zelf Google-API-toegang regelen:

- [JoachimVN/Personal-Dashboard](https://github.com/JoachimVN/Personal-Dashboard): agenda, mail, weer en Spotify op één pagina (zelf hosten).
- [Daniel-VergaraM/Dash](https://github.com/Daniel-VergaraM/Dash): taken, Google Agenda, notities en Drive (Express-server).
- [kmirzavaziri/personal-dashboard](https://github.com/kmirzavaziri/personal-dashboard): taken, agenda en meer (Flask plus YAML-bestanden).
- [Dalvelac/Tasker](https://github.com/Dalvelac/Tasker): taken, planning en agendaweergaven.
- [Glance](https://github.com/glanceapp/glance), [Homepage](https://github.com/gethomepage/homepage) en [Dashy](https://github.com/Lissy93/dashy): mooie startpagina's met widgets, vooral voor homelabs. Mail en taken zitten er niet in.
- [Super Productivity](https://github.com/johannesjo/super-productivity): open-source takenplanner met tijdregistratie en agenda-integratie.

Geen van deze projecten combineert je mail, taken en agenda met een assistent die meeplant, zonder dat je zelf iets hoeft te hosten. Daarom is de Regiekamer zelf gebouwd.

---

# Ook in deze repo: ATEM-regie

In [`atem-regie/`](atem-regie/) staat een programma voor de Mac dat naar je microfoons luistert en de ATEM Mini Pro automatisch de juiste camera laat kiezen. Het kan ook een presentatie met de spreker in een kader of ernaast in beeld zetten, en het heeft een geluidscheck die per mic advies geeft. Begin bij [`atem-regie/README.md`](atem-regie/README.md).
