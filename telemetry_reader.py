"""Liest moeglichst viele Telemetriedaten einer Drohne via MAVSDK aus und sendet
sie als aggregiertes JSON per HTTP-POST an einen (ungesicherten) REST-Endpoint.

Es werden alle in MAVSDK verfuegbaren Telemetrie-Streams abonniert und in einem
gemeinsamen Zustand zusammengefuehrt. In festen Intervallen wird der komplette
Zustand als ein JSON-Dokument gesendet. Streams, die die Drohne nicht liefert
oder nicht unterstuetzt, stehen im JSON auf ``null``.

Unterstuetzte Verbindungsmodi:
  * "server"  - Python startet den mavsdk_server selbst (Standard).
  * "attach"  - an einen bereits laufenden mavsdk_server andocken.

Beispiel:
  python telemetry_reader.py \\
      --http-host 127.0.0.1 --http-port 8000 --route /telemetry \\
      --drone-name "Drohne-1" --drone-id 1 --print
"""

import argparse
import asyncio
import contextlib
import enum
import json
import math
import time

import aiohttp

from mavsdk import System
from mavsdk.telemetry import TelemetryError


# ---------------------------------------------------------------------------
# Telemetrie-Streams und zugehoerige set_rate_*-Methoden
# ---------------------------------------------------------------------------

# Alle abonnierbaren Telemetrie-Streams (Name -> Telemetry-Methodenname).
STREAM_NAMES = [
    "actuator_control_target",
    "actuator_output_status",
    "altitude",
    "armed",
    "attitude_angular_velocity_body",
    "attitude_euler",
    "attitude_quaternion",
    "battery",
    "distance_sensor",
    "fixedwing_metrics",
    "flight_mode",
    "gps_info",
    "ground_truth",
    "heading",
    "health",
    "health_all_ok",
    "home",
    "imu",
    "in_air",
    "landed_state",
    "odometry",
    "position",
    "position_velocity_ned",
    "raw_gps",
    "raw_imu",
    "rc_status",
    "scaled_imu",
    "scaled_pressure",
    "status_text",
    "unix_epoch_time",
    "velocity_ned",
    "vtol_state",
    "wind",
]


# ---------------------------------------------------------------------------
# Serialisierung von MAVSDK-Nachrichten -> JSON-faehige Strukturen
# ---------------------------------------------------------------------------

def to_serializable(obj):
    """Wandelt ein MAVSDK-Nachrichtenobjekt rekursiv in JSON-faehige Typen um.

    * Enums (z.B. FlightMode) -> Name als String.
    * Objekte mit __dict__ (Nachrichten/Untertypen) -> verschachteltes Dict.
    * Listen/Tupel -> Listen.
    * NaN / Inf -> None (damit json.dumps(allow_nan=False) durchlaeuft).
    """
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, enum.Enum):
        return obj.name
    if isinstance(obj, (list, tuple)):
        return [to_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {key: to_serializable(value) for key, value in obj.items()}
    if hasattr(obj, "__dict__"):
        return {key: to_serializable(value) for key, value in vars(obj).items()}
    # Fallback: alles andere als String darstellen.
    return str(obj)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telemetrie einer MAVLink-Drohne als JSON per HTTP-POST senden.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # MAVSDK-Verbindung
    parser.add_argument(
        "--mode",
        choices=("server", "attach"),
        default="server",
        help="'server': Python startet den mavsdk_server selbst. "
        "'attach': an einen bereits laufenden mavsdk_server andocken.",
    )
    parser.add_argument(
        "--connection",
        default="udpin://0.0.0.0:14550",
        help="MAVLink-Verbindungs-URL (nur Modus 'server'). "
        "Lauschen: udpin://0.0.0.0:14550, aktiv verbinden: udpout://10.0.0.1:14555.",
    )
    parser.add_argument(
        "--server-host",
        default="localhost",
        help="Host des laufenden mavsdk_server (nur Modus 'attach').",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=50051,
        help="gRPC-Port des mavsdk_server (nur Modus 'attach').",
    )

    # HTTP-Ziel (ungesicherter REST-Endpoint, keine Authentifizierung)
    parser.add_argument(
        "--http-host",
        required=True,
        help="IP/Host des Ziel-Servers, an den die POST-Requests gehen.",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=8000,
        help="Port des Ziel-Servers.",
    )
    parser.add_argument(
        "--route",
        required=True,
        help="Route/Pfad des REST-Endpoints, z.B. /telemetry.",
    )

    # Drohnen-Identitaet (statisch, im JSON enthalten)
    parser.add_argument(
        "--drone-name",
        required=True,
        help="Statischer Name der Drohne (wird ins JSON geschrieben).",
    )
    parser.add_argument(
        "--drone-id",
        required=True,
        help="Statische ID der Drohne (wird ins JSON geschrieben).",
    )

    # Raten / Ausgabe
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="POST-Intervall in Sekunden.",
    )
    parser.add_argument(
        "--rate-hz",
        type=float,
        default=5.0,
        help="Ziel-Rate fuer Best-Effort set_rate_* der Streams (0 = nicht setzen).",
    )
    parser.add_argument(
        "--print",
        dest="print_json",
        action="store_true",
        help="Das gesendete JSON zusaetzlich in der Konsole ausgeben.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Verbindung
# ---------------------------------------------------------------------------

async def connect(args: argparse.Namespace) -> System:
    """Stellt die Verbindung gemaess gewaehltem Modus her und wartet, bis sie steht."""
    if args.mode == "attach":
        print(
            f"[Verbindung] Docke an laufenden mavsdk_server an "
            f"({args.server_host}:{args.server_port}) ..."
        )
        drone = System(mavsdk_server_address=args.server_host, port=args.server_port)
        await drone.connect()
    else:
        print(f"[Verbindung] Starte mavsdk_server und verbinde via {args.connection} ...")
        drone = System()
        await drone.connect(system_address=args.connection)

    print("[Verbindung] Warte auf Drohne ...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("[Verbindung] Drohne verbunden.")
            break

    return drone


# ---------------------------------------------------------------------------
# Best-Effort set_rate_* (+ Capability-Report)
# ---------------------------------------------------------------------------

async def apply_rates(drone: System, rate_hz: float) -> None:
    """Versucht fuer jeden Stream set_rate_*(rate_hz) und loggt das Ergebnis.

    Erfolg deutet darauf hin, dass der Autopilot den Stream unterstuetzt;
    ein TelemetryError deutet auf fehlende Unterstuetzung hin.
    """
    if rate_hz <= 0:
        print("[Rate] set_rate_* uebersprungen (--rate-hz 0).")
        return

    print(f"[Rate] Setze Streamraten auf {rate_hz} Hz (Best-Effort) ...")
    supported, unsupported = [], []
    for name in STREAM_NAMES:
        setter = getattr(drone.telemetry, f"set_rate_{name}", None)
        if setter is None:
            continue  # z.B. raw_gps, wind: kein set_rate vorhanden
        try:
            await setter(rate_hz)
            supported.append(name)
        except TelemetryError as exc:
            unsupported.append(f"{name} ({exc})")

    print(f"[Capability] set_rate erfolgreich ({len(supported)}): "
          f"{', '.join(supported) if supported else '-'}")
    if unsupported:
        print(f"[Capability] set_rate abgelehnt ({len(unsupported)}): "
              f"{', '.join(unsupported)}")


# ---------------------------------------------------------------------------
# Producer: ein Stream je Task aktualisiert den gemeinsamen Zustand
# ---------------------------------------------------------------------------

async def consume_stream(drone: System, name: str, latest: dict) -> None:
    """Abonniert einen Telemetrie-Stream und schreibt den letzten Wert nach latest[name]."""
    method = getattr(drone.telemetry, name)
    try:
        async for msg in method():
            latest[name] = to_serializable(msg)
    except TelemetryError as exc:
        # Stream nicht verfuegbar -> Wert bleibt None/null.
        print(f"[Stream] '{name}' nicht verfuegbar: {exc}")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # robust bleiben, einzelne Streams duerfen nicht alles killen
        print(f"[Stream] '{name}' Fehler: {exc!r}")


# ---------------------------------------------------------------------------
# Sender: postet den gesamten Zustand als ein JSON-Dokument
# ---------------------------------------------------------------------------

async def post_loop(args: argparse.Namespace, latest: dict) -> None:
    url = f"http://{args.http_host}:{args.http_port}{args.route}"
    print(f"[HTTP] Sende Gesamt-JSON alle {args.interval}s an {url}")

    async with aiohttp.ClientSession() as session:
        while True:
            payload = {
                "name": args.drone_name,
                "id": args.drone_id,
                "timestamp": time.time(),
                # flache Kopie: Werte sind bereits fertige Dicts/None
                "telemetry": dict(latest),
            }
            body = json.dumps(payload, allow_nan=False)

            if args.print_json:
                print(body)

            try:
                async with session.post(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    await resp.read()
                    if resp.status >= 400:
                        print(f"[HTTP] Antwort {resp.status} von {url}")
            except aiohttp.ClientError as exc:
                print(f"[HTTP] Senden fehlgeschlagen: {exc}")

            await asyncio.sleep(args.interval)


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

async def run() -> None:
    args = parse_args()
    drone = await connect(args)

    await apply_rates(drone, args.rate_hz)

    # Gemeinsamer Zustand: alle Streams initial null.
    latest = {name: None for name in STREAM_NAMES}

    print(f"[Telemetrie] Abonniere {len(STREAM_NAMES)} Streams. Beenden mit Strg+C.\n")

    tasks = [
        asyncio.ensure_future(consume_stream(drone, name, latest))
        for name in STREAM_NAMES
    ]
    tasks.append(asyncio.ensure_future(post_loop(args, latest)))

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[Beendet] Telemetrie-Weiterleitung gestoppt.")


if __name__ == "__main__":
    main()
