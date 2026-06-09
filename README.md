# MavlinkImport

Liest **möglichst viele** Telemetriedaten einer Drohne über
[MAVSDK-Python](https://mavsdk.mavlink.io/main/en/python/) aus und sendet sie als
**ein aggregiertes JSON-Dokument** per HTTP-POST an einen REST-Endpoint.

Es werden alle in MAVSDK verfügbaren Telemetrie-Streams abonniert und in einem
gemeinsamen Zustand zusammengeführt. In festen Intervallen wird der komplette
Zustand gesendet. Streams, die die Drohne nicht liefert/unterstützt, stehen im
JSON auf `null`.

## Voraussetzungen

* Python 3.8+
* Auf Windows: **Microsoft Visual C++ Redistributable x64** muss installiert sein
  (sonst fehlen `MSVCP140.dll` / `VCRUNTIME140.dll`).
* Drohne sendet MAVLink per UDP (im getesteten Setup vom Autopilot `10.0.0.1:14555`,
  System ID 1, über WiFi).
* Ein erreichbarer REST-Endpoint, der `POST` mit JSON-Body akzeptiert
  (**ohne Authentifizierung**).

## Installation

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Schnellstart

```bash
python telemetry_reader.py \
    --http-host 127.0.0.1 --http-port 8000 --route /telemetry \
    --drone-name "Drohne-1" --drone-id 1 --print
```

Beenden mit `Strg+C`.

## Alle Parameter

### MAVSDK-Verbindung

| Parameter         | Default                  | Bedeutung |
|-------------------|--------------------------|-----------|
| `--mode`          | `server`                 | `server`: Python startet den `mavsdk_server` selbst. `attach`: an einen laufenden `mavsdk_server` andocken. |
| `--connection`    | `udpin://0.0.0.0:14550`  | MAVLink-URL (nur Modus `server`). Lauschen: `udpin://0.0.0.0:14550`, aktiv verbinden: `udpout://10.0.0.1:14555`. |
| `--server-host`   | `localhost`              | Host des laufenden `mavsdk_server` (nur Modus `attach`). |
| `--server-port`   | `50051`                  | gRPC-Port des `mavsdk_server` (nur Modus `attach`). |

### HTTP-Ziel (Pflicht)

| Parameter       | Default     | Bedeutung |
|-----------------|-------------|-----------|
| `--http-host`   | *(Pflicht)* | IP/Host des Ziel-Servers, an den die POST-Requests gehen. |
| `--http-port`   | `8000`      | Port des Ziel-Servers. |
| `--route`       | *(Pflicht)* | Route/Pfad des REST-Endpoints, z.B. `/telemetry`. |

Die Ziel-URL wird daraus zusammengesetzt: `http://{http-host}:{http-port}{route}`.
Der Endpoint ist ungesichert — es werden keine Auth-Header/Tokens gesendet.

### Drohnen-Identität (Pflicht, statisch)

| Parameter       | Default     | Bedeutung |
|-----------------|-------------|-----------|
| `--drone-name`  | *(Pflicht)* | Statischer Name der Drohne, wird ins JSON geschrieben. |
| `--drone-id`    | *(Pflicht)* | Statische ID der Drohne, wird ins JSON geschrieben. |

### Raten / Ausgabe

| Parameter      | Default | Bedeutung |
|----------------|---------|-----------|
| `--interval`   | `1.0`   | POST-Intervall in Sekunden (wie oft das Gesamt-JSON gesendet wird). |
| `--rate-hz`    | `5.0`   | Ziel-Rate für Best-Effort `set_rate_*` der Streams. `0` = nicht setzen. |
| `--print`      | *(aus)* | Das gesendete JSON zusätzlich in der Konsole ausgeben. |

## Gesendetes JSON

Das gepostete Dokument enthält die Drohnen-Identität, einen Zeitstempel und unter
`telemetry` **alle** Stream-Namen. Nicht gelieferte/unterstützte Streams sind `null`:

```json
{
  "name": "Drohne-1",
  "id": "1",
  "timestamp": 1733740800.123,
  "telemetry": {
    "position": {
      "latitude_deg": 47.1,
      "longitude_deg": 8.5,
      "absolute_altitude_m": 500.0,
      "relative_altitude_m": 10.0
    },
    "flight_mode": "HOLD",
    "battery": { "id": 0, "voltage_v": 12.3, "remaining_percent": 0.87 },
    "wind": null,
    "...": "alle 33 Stream-Schlüssel; nicht geliefert => null"
  }
}
```

Abonnierte Streams (alle 33): `actuator_control_target`, `actuator_output_status`,
`altitude`, `armed`, `attitude_angular_velocity_body`, `attitude_euler`,
`attitude_quaternion`, `battery`, `distance_sensor`, `fixedwing_metrics`,
`flight_mode`, `gps_info`, `ground_truth`, `heading`, `health`, `health_all_ok`,
`home`, `imu`, `in_air`, `landed_state`, `odometry`, `position`,
`position_velocity_ned`, `raw_gps`, `raw_imu`, `rc_status`, `scaled_imu`,
`scaled_pressure`, `status_text`, `unix_epoch_time`, `velocity_ned`, `vtol_state`,
`wind`.

## Capability-Report

Beim Start versucht das Programm für jeden Stream `set_rate_*(--rate-hz)`. Erfolg
deutet darauf hin, dass der Autopilot den Stream unterstützt, ein abgelehnter
Aufruf auf fehlende Unterstützung. Das Ergebnis wird als Capability-Report geloggt
(`[Capability] set_rate erfolgreich: ...` / `... abgelehnt: ...`). MAVSDK bietet
keine fertige Liste unterstützter Telemetrie — das ist der praktikable Weg, es zur
Laufzeit zu ermitteln. Streams, die nie Daten liefern, bleiben im JSON auf `null`.

## Verbindungsmodi

### Modus 1 — Python startet den Server selbst (Standard)

```bash
python telemetry_reader.py --http-host 127.0.0.1 --route /telemetry \
    --drone-name "Drohne-1" --drone-id 1
# entspricht --mode server --connection udpin://0.0.0.0:14550
```

### Modus 2 — an einen laufenden mavsdk_server andocken

Server zuerst manuell starten (z.B. auf Windows):

```bash
.\mavsdk_server_win_x64.exe udpin://0.0.0.0:14550
```

Dann andocken:

```bash
python telemetry_reader.py --mode attach --server-host localhost --server-port 50051 \
    --http-host 127.0.0.1 --route /telemetry --drone-name "Drohne-1" --drone-id 1
```

## Test-Endpoint (lokaler Echo-Server)

Zum Ausprobieren ein minimaler Empfänger, der eingehende POSTs ausgibt:

```python
# echo_server.py  ->  python echo_server.py
from aiohttp import web

async def handler(request):
    print(await request.json())
    return web.json_response({"ok": True})

app = web.Application()
app.router.add_post("/telemetry", handler)
web.run_app(app, host="127.0.0.1", port=8000)
```

## Mehrere Drohnen

Pro Drohne ein eigener `mavsdk_server` mit eigenem UDP-Port (14550, 14551, ...)
und eigenem gRPC-Port. Im Skript dann `--server-port 50052` usw. setzen sowie je
Drohne eigene `--drone-name`/`--drone-id`. Mehrere Python-Clients an einem Server
funktionieren nicht zuverlässig (Streams werden "geklaut").
