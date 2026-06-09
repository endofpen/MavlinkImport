"""Simuliert den REST-Endpoint fuer telemetry_reader.py.

Startet einen kleinen HTTP-Server, nimmt POST-Requests entgegen und gibt den
empfangenen JSON-Body uebersichtlich in der Konsole aus. Antwortet mit
HTTP 200 und {"ok": true}.

Beispiel:
  python echo_server.py
  python echo_server.py --host 0.0.0.0 --port 8000 --route /telemetry
  python echo_server.py --compact      # JSON einzeilig statt eingerueckt

Passend dazu der Sender:
  python telemetry_reader.py --http-host 127.0.0.1 --http-port 8000 \\
      --route /telemetry --drone-name "Drohne-1" --drone-id 1
"""

import argparse
import json
from datetime import datetime

from aiohttp import web


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mock-REST-Endpoint, der eingehende POSTs in der Konsole ausgibt.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host/Interface zum Lauschen.")
    parser.add_argument("--port", type=int, default=8000, help="Port zum Lauschen.")
    parser.add_argument(
        "--route",
        default="/telemetry",
        help="Pfad, der POST-Requests akzeptiert.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="JSON einzeilig ausgeben statt eingerueckt.",
    )
    return parser.parse_args()


def make_handler(compact: bool):
    counter = {"n": 0}

    async def handler(request: web.Request) -> web.Response:
        counter["n"] += 1
        now = datetime.now().strftime("%H:%M:%S")
        peer = request.remote

        try:
            data = await request.json()
            if compact:
                body = json.dumps(data, ensure_ascii=False)
            else:
                body = json.dumps(data, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            raw = await request.text()
            print(f"\n--- POST #{counter['n']}  {now}  von {peer}  (kein JSON) ---")
            print(raw)
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)

        print(f"\n--- POST #{counter['n']}  {now}  von {peer} ---")
        print(body)
        return web.json_response({"ok": True})

    return handler


def main() -> None:
    args = parse_args()

    app = web.Application()
    app.router.add_post(args.route, make_handler(args.compact))

    print(
        f"[Mock-Endpoint] Lausche auf http://{args.host}:{args.port}{args.route} "
        f"(POST). Beenden mit Strg+C."
    )
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
