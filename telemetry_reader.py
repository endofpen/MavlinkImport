"""Liest Telemetriedaten einer Drohne via MAVSDK aus und gibt sie in der Konsole aus.

Unterstuetzt zwei Verbindungsmodi:

  * Modus "server"   - Python startet den mavsdk_server selbst und verbindet sich
                       per UDP zur Drohne (Standard).
  * Modus "attach"   - Es wird an einen bereits laufenden mavsdk_server angedockt
                       (z.B. mavsdk_server_win_x64.exe).

Beispiele:
  python telemetry_reader.py
  python telemetry_reader.py --connection udpin://0.0.0.0:14550
  python telemetry_reader.py --mode attach --server-host localhost --server-port 50051
"""

import argparse
import asyncio
import contextlib

from mavsdk import System


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telemetriedaten einer MAVLink-Drohne in der Konsole ausgeben.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
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
        help="MAVLink-Verbindungs-URL (nur fuer Modus 'server'). "
        "Lauschen: udpin://0.0.0.0:14550, aktiv verbinden: udpout://10.0.0.1:14555.",
    )
    parser.add_argument(
        "--server-host",
        default="localhost",
        help="Host des laufenden mavsdk_server (nur fuer Modus 'attach').",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=50051,
        help="gRPC-Port des mavsdk_server (nur fuer Modus 'attach').",
    )
    return parser.parse_args()


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


async def print_position(drone: System) -> None:
    async for p in drone.telemetry.position():
        print(
            f"[Position]  lat={p.latitude_deg:.7f}  lon={p.longitude_deg:.7f}  "
            f"rel_alt={p.relative_altitude_m:.2f} m  abs_alt={p.absolute_altitude_m:.2f} m"
        )


async def print_attitude(drone: System) -> None:
    async for a in drone.telemetry.attitude_euler():
        print(
            f"[Lage]      roll={a.roll_deg:6.1f} deg  "
            f"pitch={a.pitch_deg:6.1f} deg  yaw={a.yaw_deg:6.1f} deg"
        )


async def print_battery(drone: System) -> None:
    async for b in drone.telemetry.battery():
        print(
            f"[Batterie]  {b.voltage_v:.2f} V  "
            f"{b.remaining_percent * 100:.0f} %"
        )


async def print_gps_info(drone: System) -> None:
    async for g in drone.telemetry.gps_info():
        print(f"[GPS]       Satelliten={g.num_satellites}  Fix={g.fix_type}")


async def print_velocity(drone: System) -> None:
    async for v in drone.telemetry.velocity_ned():
        print(
            f"[Geschw.]   N={v.north_m_s:5.2f}  E={v.east_m_s:5.2f}  "
            f"D={v.down_m_s:5.2f} m/s"
        )


async def print_flight_mode(drone: System) -> None:
    async for mode in drone.telemetry.flight_mode():
        print(f"[Flugmodus] {mode}")


async def run() -> None:
    args = parse_args()
    drone = await connect(args)

    print("[Telemetrie] Starte Streams. Beenden mit Strg+C.\n")

    tasks = [
        asyncio.ensure_future(print_position(drone)),
        asyncio.ensure_future(print_attitude(drone)),
        asyncio.ensure_future(print_battery(drone)),
        asyncio.ensure_future(print_gps_info(drone)),
        asyncio.ensure_future(print_velocity(drone)),
        asyncio.ensure_future(print_flight_mode(drone)),
    ]

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
        print("\n[Beendet] Telemetrie-Ausgabe gestoppt.")


if __name__ == "__main__":
    main()
