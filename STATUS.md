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

Jonathan starter!

#### Autonomous pipeline [WIP]
##### Pipeline inspection
##### Docking med aruco

Aruco marker detection har blitt delvis implementert
Noe er startet her, men ikke mye, gjerne kontribuer og dokumentar hva du har gjort!

