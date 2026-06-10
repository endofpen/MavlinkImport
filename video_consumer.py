"""Beispiel-Konsument fuer einen von video_distributor.py verteilten Stream.

Zeigt, wie ein Python-/CV-Service den Videostream latenzarm per RTSP abgreift:
liest mit OpenCV (FFmpeg-Backend, kleiner Puffer, TCP-Transport), misst die
effektive FPS und zeigt optional ein Vorschaufenster. Dient als belegbarer
Abnahmetest (Gegenstueck zu echo_server.py fuer die Telemetrie).

Voraussetzung (separat, nicht in requirements.txt):
  pip install opencv-python

Beispiel:
  python video_consumer.py rtsp://127.0.0.1:8554/fpv
  python video_consumer.py rtsp://127.0.0.1:8554/fpv --show

Alternative ganz ohne Python:
  ffplay -fflags nobuffer -flags low_delay rtsp://127.0.0.1:8554/fpv
"""

import argparse
import os
import sys
import time

# Latenzarm: RTSP ueber TCP erzwingen, bevor cv2 das FFmpeg-Backend initialisiert.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RTSP-Stream latenzarm mit OpenCV konsumieren (Abnahmetest).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="rtsp://127.0.0.1:8554/fpv",
        help="Stream-URL (RTSP).",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Vorschaufenster anzeigen (benoetigt GUI). Beenden mit 'q'.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        import cv2
    except ImportError:
        print("[Fehler] OpenCV fehlt. Installieren mit: pip install opencv-python")
        sys.exit(1)

    print(f"[Konsum] Verbinde mit {args.url} ...")
    cap = cv2.VideoCapture(args.url, cv2.CAP_FFMPEG)
    # Internen Puffer klein halten -> niedrige Latenz.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("[Fehler] Stream konnte nicht geoeffnet werden. Laeuft der Distributor?")
        sys.exit(1)

    frames = 0
    last = time.monotonic()
    print("[Konsum] Verbunden. Beenden mit Strg+C.\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[Konsum] Kein Frame empfangen (Stream-Unterbrechung?).")
                time.sleep(0.5)
                continue

            frames += 1
            now = time.monotonic()
            if now - last >= 1.0:
                height, width = frame.shape[:2]
                print(f"[Konsum] {frames} fps, Frame {width}x{height}")
                frames = 0
                last = now

            if args.show:
                cv2.imshow("video_consumer", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("\n[Beendet] Konsum gestoppt.")
    finally:
        cap.release()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
