# MavlinkImport

Liest die Telemetriedaten einer Drohne ueber [MAVSDK-Python](https://mavsdk.mavlink.io/main/en/python/)
aus und gibt sie in der Konsole aus.

## Voraussetzungen

* Python 3.8+
* Auf Windows: **Microsoft Visual C++ Redistributable x64** muss installiert sein
  (sonst fehlen `MSVCP140.dll` / `VCRUNTIME140.dll`).
* Drohne sendet MAVLink per UDP (im getesteten Setup vom Autopilot `10.0.0.1:14555`,
  System ID 1, ueber WiFi).

## Installation

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Verwendung

### Modus 1 - Python startet den Server selbst (Standard)

MAVSDK-Python bringt den `mavsdk_server` mit und startet ihn automatisch:

```bash
python telemetry_reader.py
# entspricht:
python telemetry_reader.py --mode server --connection udpin://0.0.0.0:14550
```

* `udpin://0.0.0.0:14550` lauscht auf UDP-Port 14550.
* `udpout://10.0.0.1:14555` verbindet sich aktiv zum Autopiloten.

### Modus 2 - an einen laufenden mavsdk_server andocken

Server zuerst manuell starten (z.B. auf Windows):

```bash
.\mavsdk_server_win_x64.exe udpin://0.0.0.0:14550
```

Der Server lauscht auf UDP-Port 14550 und stellt gRPC auf Port 50051 bereit.
Dann das Skript andocken:

```bash
python telemetry_reader.py --mode attach --server-host localhost --server-port 50051
```

## Ausgegebene Telemetrie

Folgende Streams werden parallel gelesen und ausgegeben:

| Stream         | Inhalt                                              |
|----------------|-----------------------------------------------------|
| Position       | Lat/Lon, relative und absolute Hoehe                |
| Lage           | Roll/Pitch/Yaw (Euler)                              |
| Batterie       | Spannung, Restkapazitaet                            |
| GPS            | Anzahl Satelliten, Fix-Typ                          |
| Geschwindigkeit| NED-Geschwindigkeit (Nord/Ost/Unten)                |
| Flugmodus      | Aktueller Flugmodus                                 |

Beenden mit `Strg+C`.

## Mehrere Drohnen

Pro Drohne ein eigener `mavsdk_server` mit eigenem UDP-Port (14550, 14551, ...)
und eigenem gRPC-Port. Im Skript dann `--server-port 50052` usw. setzen.
Mehrere Python-Clients an einem Server funktionieren nicht zuverlaessig
(Streams werden "geklaut").
