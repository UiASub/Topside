# Prosjekt status

Denne filen skal inneholde (så godt vi greier) nåværende status for topside.
Dvs. hva som er integrert, hva som er wip - og gjerne hva som må gjøres eller blokker, og hva som ikke er startet.

#### Joystick [FERDIG] (ca.)
Integrert i topside - inputs lagres i `data/data.json`.
Knapper må fortsatt lables og bestemme hva de gjør.

#### Kamera [WIP]
Storm integrer i topside. Raspberry pi camera, ikke IP camera er siste oppdatering.

#### Frontend [FERDIG]
Funksjonelt ferdig. Hvis noen ønsker å endre styling på den, evt implementere 3D modellen av roveren kan dette gjøres.

#### Sende data til rover [IKKE STARTET]
**Koble til rover over TCP.**
**Sende ned -> rover data/data.json** (kun felt som er relevant).
**Motta opp <- rover sin data.json str.** Deretter lagre relevante felt i topside data/data.json.

**TCP går gjennom Raspberry Pi**
**Hvordan sendes ArUco-data fra Raspberry Pi til roverens hovedprosessor?**
Aruco gjenkjenning skjer på Topside. Kun kamera streamen sendes over UDP. Aruco gjenkjenning er del av automation pipeline.
**Skal det brukes PID-kontroll for finjustering?**
Sverre (elektro) ser på PID kontroll på STM32 thrusters
- Ikke klart hva status er her.

##### Set up nede på ROV:
Inne i kanna er en Raspberry PI. Denne kommuniserer med STM32 over USB.

Topside kommuniserer 
1: TCP <-> data.json sendes begge veier.
2: UDP <- Kamera streames opp.

Raspberry PI kommuniserer over USB. Data.json sendes opp og ned.

### Oppgave:
1: Finne ut hvordan vi setter statisk ip på Raspberry PI - Hør med Storm tror han kunne dette.

2: Implementere Python funksjon som lever på raspberry pi - Leser data.json fra STM32 (nucleo). Se Topside/read_joystick.py - here er dette implementert for arduino, koden blir ca. samme.

3: Implementere Python funksjon som sender data.json over usb (serial).

4: Python program som streamer kamera over UDP til topside.

5: Python funksjonalitet på topside som mottar UDP strømmen fra 4. Se backup-usb-camera-ethernet

6: På STM32: Funksjon for å lese serial og motta data.json fra raspberry pi.

7: På STM32: Funksjon for å sende data fra STM32 til raspberry pi. Joystick repoet til uiasub her er dette implementert for arduino blir ca samme kode.

8: På STM32: gjøre om data.json som er mottat til faktisk thrust verdier.

9: På STM32: Håndtere at roveren ligger stille i vannet


#### Autonomous pipeline [WIP]
##### Pipeline inspection
##### Docking med aruco

Aruco marker detection har blitt delvis implementert
Noe er startet her, men ikke mye, gjerne kontribuer og dokumentar hva du har gjort!

