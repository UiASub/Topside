# Forklaring av data.json

Filen `data/data.json` inneholder Topside sin modell av sensorverdier, og hva topside sender ned til rover.

Filen ser slik ut:
```
{
    "Nøkkel1" : Verdi (f.eks 0 eller 1.)
    "Nøkkel2" : 256
}
```

Den kan også inneholde nested values altså

```
{
    "Buttons" : {
        "Button1" : 0,    // Knappen ikke trykket inne
        "Button2" : 1     // Knappen er trykket inne
    }
}
```

Filen leses med json librariet:
```python
import json      # laster json librariet

# Åpner filen og laster data inn i __data_dict__.
with open('data/data.json', 'r') as file:
    data_dict = json.load(file)            # Endre navnet til __data_dict__ til det du ønsker.
```

Når den er lest inn leser du verdier med syntaksen
```
x = data_dict["Nøkkel"]
```

Nøkler som er nested lese med
```
x = data_dict["Nøkkel"]["Undernøkkel"]

# Eksempel:
y = data_dict["Buttons"]["Button1"]
```

## Oversikt over verdier

#### Thrust:
`"Thrust" : [x,y,z,pitch,roll,yaw]` 
Liste (array) med 6 verdier. `data_dict["Trust"][1]` gir y verdien.

#### Buttons
Knapper fra joystick - 0 eller 1. (ikke holdt inne, vs holdt inne.)
```
"Buttons" : {
    "button_surface" : 0    // Gå til surface knapp
}
```

#### thrusters
Målte verdier på thrusterne. Eks:
```
"thrusters": {
        "U_FWD_P": {
            "power": 400,
            "temp": 20
        }
}
```
Hver har `"power"` og `"temp"`.

#### 9dof
Målte 9dof verdier - `"acceleration"`, `"gyroscope"`, og `"magnetometer"`.
Hver har `x`, `y`, og `z` verdi.\

Eksempel:
```
"9dof": {
    "acceleration": {
        "x": 0.02,
        "y": -0.01,
        "z": 9.81
    },
    "gyroscope": {
        "x": 0.01,
        "y": 0.02,
        "z": 0.00
    },
    "magnetometer": {
        "x": 30.6,
        "y": -22.3,
        "z": 15.5
    }
}
```

#### Lights
Lys.

Eksempel:
```
"lights": {
    "Light1": 50,
    "Light2": 50,
    "Light3": 50,
    "Light4": 50
}
```

#### Battery
Batteri. Prosent.

```
"battery": 100
```

#### Depth
Dybde.
```
"depth": {
    "dpt": 123,
    "dptSet": 124
}
```

`"dpt"` er målt dybde.
`"dptSet"` er dybden som den forsøker å nå (target).
