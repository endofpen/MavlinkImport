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
| `--rate-hz`    | `0.0`   | Ziel-Rate für Best-Effort `set_rate_*` der Streams. `0` = nicht setzen (Standard); `>0` aktiviert das Setzen. |
| `--print`      | *(aus)* | Das gesendete JSON zusätzlich in der Konsole ausgeben. |

## Gesendetes JSON

Das gepostete Dokument enthält die Drohnen-Identität, einen Zeitstempel und unter
`telemetry` **alle** Stream-Namen. Nicht gelieferte/unterstützte Streams sind `null`:

Beispiel-Dump (am Mock-Endpoint empfangen):

```json
{
  "name": "Drohne-Maverick",
  "id": "666",
  "timestamp": 1781016780.5282433,
  "telemetry": {
    "actuator_control_target": null,
    "actuator_output_status": null,
    "altitude": null,
    "armed": false,
    "attitude_angular_velocity_body": {
      "roll_rad_s": 0.0,
      "pitch_rad_s": 0.0,
      "yaw_rad_s": 0.0
    },
    "attitude_euler": {
      "roll_deg": -34.099998474121094,
      "pitch_deg": 4.699999809265137,
      "yaw_deg": 216.6999969482422,
      "timestamp_us": 607812000
    },
    "attitude_quaternion": null,
    "battery": {
      "id": 0,
      "temperature_degc": null,
      "voltage_v": 22.98000144958496,
      "current_battery_a": 0.949999988079071,
      "capacity_consumed_ah": 0.16200000047683716,
      "remaining_percent": 53.0,
      "time_remaining_s": null,
      "battery_function": "UNKNOWN"
    },
    "distance_sensor": null,
    "fixedwing_metrics": {
      "airspeed_m_s": 0.0,
      "throttle_percentage": 0.8499999642372131,
      "climb_rate_m_s": 0.0,
      "groundspeed_m_s": 6.909999847412109,
      "heading_deg": 216.0,
      "absolute_altitude_m": 248.0699920654297
    },
    "flight_mode": "UNKNOWN",
    "gps_info": {
      "num_satellites": 5,
      "fix_type": "FIX_3D"
    },
    "ground_truth": null,
    "heading": {
      "heading_deg": 2.16
    },
    "health": {
      "is_gyrometer_calibration_ok": true,
      "is_accelerometer_calibration_ok": true,
      "is_magnetometer_calibration_ok": false,
      "is_local_position_ok": true,
      "is_global_position_ok": true,
      "is_home_position_ok": false,
      "is_armable": false
    },
    "health_all_ok": false,
    "home": null,
    "imu": null,
    "in_air": null,
    "landed_state": null,
    "odometry": null,
    "position": {
      "latitude_deg": 50.6256292,
      "longitude_deg": 6.8480631999999995,
      "absolute_altitude_m": 248.07000732421875,
      "relative_altitude_m": 248.07000732421875
    },
    "position_velocity_ned": null,
    "raw_gps": {
      "timestamp_us": 608314813,
      "latitude_deg": 50.625627099999996,
      "longitude_deg": 6.8480215,
      "absolute_altitude_m": 246.92001342773438,
      "hdop": 0.0,
      "vdop": 0.0,
      "velocity_m_s": 2.059999942779541,
      "cog_deg": 64.5999984741211,
      "altitude_ellipsoid_m": 246.92001342773438,
      "horizontal_uncertainty_m": 24.940000534057617,
      "vertical_uncertainty_m": 13.689001083374023,
      "velocity_uncertainty_m_s": 5.046000003814697,
      "heading_uncertainty_deg": 42949.671875,
      "yaw_deg": 0.0
    },
    "raw_imu": null,
    "rc_status": {
      "was_available_once": false,
      "is_available": false,
      "signal_strength_percent": null
    },
    "scaled_imu": null,
    "scaled_pressure": null,
    "status_text": null,
    "unix_epoch_time": null,
    "velocity_ned": {
      "north_m_s": 2.0899999141693115,
      "east_m_s": 6.589999675750732,
      "down_m_s": -3.1499998569488525
    },
    "vtol_state": null,
    "wind": null
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

Standardmäßig werden **keine** Streamraten gesetzt. Wird `--rate-hz` auf einen Wert
`>0` gesetzt, versucht das Programm beim Start für jeden Stream
`set_rate_*(--rate-hz)`. Erfolg deutet darauf hin, dass der Autopilot den Stream
unterstützt, ein abgelehnter Aufruf auf fehlende Unterstützung. Das Ergebnis wird
als Capability-Report geloggt (`[Capability] set_rate erfolgreich: ...` /
`... abgelehnt: ...`). MAVSDK bietet
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

## Test-Endpoint (mitgelieferter Mock-Server)

Solange der echte Endpoint noch nicht existiert, simuliert `echo_server.py` ihn:
Er nimmt POST-Requests entgegen, gibt den JSON-Body übersichtlich in der Konsole
aus und antwortet mit `{"ok": true}`.

```bash
python echo_server.py
# oder mit eigenen Werten:
python echo_server.py --host 0.0.0.0 --port 8000 --route /telemetry
python echo_server.py --compact   # JSON einzeilig statt eingerückt
```

| Parameter   | Default        | Bedeutung |
|-------------|----------------|-----------|
| `--host`    | `127.0.0.1`    | Host/Interface zum Lauschen. |
| `--port`    | `8000`         | Port zum Lauschen. |
| `--route`   | `/telemetry`   | Pfad, der POST-Requests akzeptiert. |
| `--compact` | *(aus)*        | JSON einzeilig ausgeben statt eingerückt. |

Typischer Ablauf in zwei Terminals:

```bash
# Terminal 1 – Mock-Endpoint
python echo_server.py --port 8000 --route /telemetry

# Terminal 2 – Telemetrie-Sender
python telemetry_reader.py --http-host 127.0.0.1 --http-port 8000 \
    --route /telemetry --drone-name "Drohne-1" --drone-id 1
```

## Docker

Das Image bringt Python, die Abhängigkeiten und den (statisch gelinkten,
mitgelieferten) `mavsdk_server` mit. **Alle CLI-Parameter bleiben erhalten** — sie
werden per `ENTRYPOINT` an `telemetry_reader.py` durchgereicht.

### Bauen

```bash
docker build -t mavlinkimport .
```

### Einzelnen Container starten

Alles nach dem Image-Namen sind die gewohnten Parameter:

```bash
docker run --rm \
    -p 14550:14550/udp \
    mavlinkimport \
    --http-host host.docker.internal --http-port 8000 --route /telemetry \
    --drone-name "Drohne-1" --drone-id 1
```

Zwei Netzwerk-Punkte sind dabei wichtig:

1. **MAVLink von der Drohne (UDP):** Im Modus `server` lauscht der Container auf
   `udpin://0.0.0.0:14550`. Der Port muss veröffentlicht werden: `-p 14550:14550/udp`.
   Unter **Linux** ist `--network host` meist robuster für Drohnen-Kommunikation
   (dann entfällt `-p`, und der Container erreicht das Drohnen-Netz direkt):
   ```bash
   docker run --rm --network host mavlinkimport \
       --http-host 127.0.0.1 --http-port 8000 --route /telemetry \
       --drone-name "Drohne-1" --drone-id 1
   ```
   Unter **Windows/macOS (Docker Desktop)** gibt es kein echtes `--network host`;
   dort `-p 14550:14550/udp` nutzen.

2. **Ziel-Endpoint:** Innerhalb des Containers ist `127.0.0.1` der Container selbst.
   Läuft der REST-Server auf dem **Host**, mit `--http-host host.docker.internal`
   darauf zeigen (Docker Desktop; unter Linux ggf.
   `--add-host=host.docker.internal:host-gateway` ergänzen). Zeigt er auf einen
   anderen Rechner, einfach dessen IP als `--http-host` angeben.

### An laufenden mavsdk_server andocken (attach)

Läuft der `mavsdk_server` außerhalb des Containers (z.B. auf dem Host):

```bash
docker run --rm mavlinkimport \
    --mode attach --server-host host.docker.internal --server-port 50051 \
    --http-host host.docker.internal --http-port 8000 --route /telemetry \
    --drone-name "Drohne-1" --drone-id 1
```

### Test-Stack mit docker compose

`docker-compose.yml` startet Sender **und** Mock-Endpoint zusammen. Der Sender
erreicht den Endpoint über den Service-Namen `echo` (`--http-host echo`):

```bash
docker compose up --build
# Logs des Endpoints sieht man im Compose-Output; stoppen mit Strg+C / docker compose down
```

Die Parameter stehen im `command:`-Block des `telemetry`-Service und können dort
angepasst werden. In Produktion den `echo`-Service entfernen und `--http-host` auf
den echten Server zeigen lassen.

## Mehrere Drohnen

Pro Drohne ein eigener `mavsdk_server` mit eigenem UDP-Port (14550, 14551, ...)
und eigenem gRPC-Port. Im Skript dann `--server-port 50052` usw. setzen sowie je
Drohne eigene `--drone-name`/`--drone-id`. Mehrere Python-Clients an einem Server
funktionieren nicht zuverlässig (Streams werden "geklaut").
