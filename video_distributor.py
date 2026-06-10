"""Speist den Videostream einer Capture-Card (HDMI->Capture-Card->USB) ein und
verteilt ihn latenzarm an mehrere Services gleichzeitig.

Das Programm orchestriert zwei externe Prozesse:

  * **FFmpeg** liest die Capture-Card (unter Windows per DirectShow) und schiebt
    sie low-latency-encodiert (H.264, ``-tune zerolatency``) als RTSP-Push in den
    Media-Server.
  * **MediaMTX** (https://github.com/bluenviron/mediamtx) nimmt diese **eine**
    Quelle entgegen und stellt sie **gleichzeitig** als RTSP / WebRTC / SRT /
    RTMP / (LL-)HLS bereit ("1 -> viele", ohne Zusatzlatenz).

Andere Python-/CV-Services ziehen den Stream bevorzugt per RTSP (oder SRT),
latenzkritische Clients per WebRTC.

Voraussetzungen:
  * FFmpeg im PATH (oder via --ffmpeg angeben).
  * MediaMTX-Binary (Windows: mediamtx.exe) im PATH oder via --mediamtx.
  * Auf Windows zusaetzlich das Microsoft Visual C++ Redistributable x64.

Beispiel:
  python video_distributor.py --list-devices
  python video_distributor.py --device "USB Video" --path fpv --print
  python video_distributor.py --test-source --path fpv   # ohne Hardware (Testbild)
"""

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Videostream einer Capture-Card einspeisen und via MediaMTX "
        "(RTSP/WebRTC/SRT/RTMP/HLS) an mehrere Services verteilen.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Quelle (Capture-Card)
    parser.add_argument(
        "--device",
        default=None,
        help="DirectShow-Geraetename der Capture-Card (Windows), "
        "z.B. \"USB Video\". Pflicht, ausser bei --list-devices/--test-source.",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Verfuegbare DirectShow-Geraete via FFmpeg auflisten und beenden.",
    )
    parser.add_argument(
        "--test-source",
        action="store_true",
        help="Statt der Capture-Card ein FFmpeg-Testbild (lavfi testsrc) "
        "einspeisen. Praktisch zum Abnehmen ohne Hardware.",
    )
    parser.add_argument(
        "--resolution",
        default="1280x720",
        help="Aufloesung der Capture-Eingabe, z.B. 1920x1080.",
    )
    parser.add_argument(
        "--framerate",
        type=int,
        default=60,
        help="Bildrate der Capture-Eingabe in fps.",
    )
    parser.add_argument(
        "--input-format",
        default="mjpeg",
        help="Pixel-/Eingangsformat der Capture-Card (dshow), "
        "typisch mjpeg oder yuyv422.",
    )

    # Encoding
    parser.add_argument(
        "--codec",
        choices=("h264", "copy"),
        default="h264",
        help="'h264': latenzarm neu encodieren (libx264, zerolatency). "
        "'copy': Stream durchreichen (nur wenn die Karte bereits H.264 liefert).",
    )
    parser.add_argument(
        "--bitrate",
        default="6M",
        help="Ziel-Bitrate fuer die H.264-Encodierung (nur --codec h264).",
    )

    # Veroeffentlichung
    parser.add_argument(
        "--path",
        default="fpv",
        help="Pfadname im Media-Server. Ergibt die Stream-URLs, z.B. /fpv.",
    )
    parser.add_argument("--rtsp-port", type=int, default=8554, help="RTSP-Port (MediaMTX).")
    parser.add_argument("--webrtc-port", type=int, default=8889, help="WebRTC-Port (MediaMTX).")
    parser.add_argument("--srt-port", type=int, default=8890, help="SRT-Port (MediaMTX).")
    parser.add_argument("--rtmp-port", type=int, default=1935, help="RTMP-Port (MediaMTX).")
    parser.add_argument("--hls-port", type=int, default=8888, help="HLS-Port (MediaMTX).")

    # Binaries / Ausgabe
    parser.add_argument(
        "--ffmpeg",
        default=None,
        help="Pfad zur FFmpeg-Binary (Default: aus PATH).",
    )
    parser.add_argument(
        "--mediamtx",
        default=None,
        help="Pfad zur MediaMTX-Binary (Default: aus PATH).",
    )
    parser.add_argument(
        "--print",
        dest="print_output",
        action="store_true",
        help="Vollstaendige Ausgabe von FFmpeg und MediaMTX in der Konsole zeigen.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Binaries finden
# ---------------------------------------------------------------------------

def resolve_binary(name: str, override: str) -> str:
    """Liefert den Pfad zur Binary (override oder aus PATH) oder beendet mit Hinweis."""
    path = override or shutil.which(name)
    if not path:
        print(
            f"[Fehler] '{name}' nicht gefunden. Bitte installieren und in den PATH "
            f"legen oder per --{name} den Pfad angeben."
        )
        sys.exit(1)
    return path


# ---------------------------------------------------------------------------
# DirectShow-Geraete auflisten
# ---------------------------------------------------------------------------

def list_devices(ffmpeg: str) -> None:
    """Listet die von FFmpeg gesehenen DirectShow-Video-Geraete auf (Windows)."""
    print("[Capture] Frage DirectShow-Geraete bei FFmpeg ab ...\n")
    # FFmpeg schreibt die Geraeteliste auf stderr und endet mit Exit-Code != 0.
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        capture_output=True,
        text=True,
    )
    output = proc.stderr or proc.stdout

    video_devices = []
    current_is_video = False
    for line in output.splitlines():
        if "(video)" in line:
            current_is_video = True
        elif "(audio)" in line:
            current_is_video = False
        match = re.search(r'"([^"]+)"', line)
        if match and current_is_video:
            video_devices.append(match.group(1))

    if video_devices:
        print("[Capture] Gefundene Video-Geraete:")
        for index, name in enumerate(video_devices):
            print(f'  [{index}] "{name}"')
        print('\nStart z.B.: python video_distributor.py --device "%s"' % video_devices[0])
    else:
        print("[Capture] Keine Video-Geraete erkannt. Rohausgabe von FFmpeg:\n")
        print(output)


# ---------------------------------------------------------------------------
# MediaMTX-Konfiguration (als Text-Template, ohne PyYAML)
# ---------------------------------------------------------------------------

def render_mediamtx_config(args: argparse.Namespace) -> str:
    """Erzeugt eine minimale mediamtx.yml: nur Adressen ueberschreiben, Publishing
    auf beliebige Pfade bleibt erlaubt (MediaMTX-Default)."""
    return textwrap.dedent(
        f"""\
        # Automatisch von video_distributor.py erzeugt.
        logLevel: info
        rtspAddress: :{args.rtsp_port}
        rtmpAddress: :{args.rtmp_port}
        hlsAddress: :{args.hls_port}
        webrtcAddress: :{args.webrtc_port}
        srtAddress: :{args.srt_port}

        paths:
          all_others:
        """
    )


# ---------------------------------------------------------------------------
# FFmpeg-Kommando: Capture -> RTSP-Push in MediaMTX
# ---------------------------------------------------------------------------

def build_ffmpeg_cmd(args: argparse.Namespace, ffmpeg: str) -> list:
    """Baut das FFmpeg-Kommando fuer latenzarme Capture + RTSP-Push."""
    target = f"rtsp://127.0.0.1:{args.rtsp_port}/{args.path}"

    cmd = [ffmpeg, "-hide_banner", "-fflags", "nobuffer", "-flags", "low_delay"]

    if args.test_source:
        # Testbild ohne Hardware (zum Abnehmen der Verteilung).
        cmd += [
            "-re",
            "-f", "lavfi",
            "-i", f"testsrc=size={args.resolution}:rate={args.framerate}",
        ]
    else:
        # DirectShow-Capture (Windows).
        cmd += [
            "-f", "dshow",
            "-rtbufsize", "100M",
            "-framerate", str(args.framerate),
            "-video_size", args.resolution,
            "-input_format", args.input_format,
            "-i", f"video={args.device}",
        ]

    if args.codec == "copy":
        cmd += ["-c:v", "copy"]
    else:
        cmd += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",
            "-pix_fmt", "yuv420p",
            "-b:v", args.bitrate,
            "-g", str(args.framerate),
        ]

    cmd += ["-an", "-f", "rtsp", "-rtsp_transport", "tcp", target]
    return cmd


# ---------------------------------------------------------------------------
# Hilfsfunktionen: auf Port warten, Prozess sauber beenden
# ---------------------------------------------------------------------------

def wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    """Pollt, bis (host, port) TCP-Verbindungen annimmt, oder bis Timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def stop_process(proc: subprocess.Popen) -> None:
    """Beendet einen Prozess hoeflich (terminate), notfalls hart (kill)."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def print_consumer_urls(args: argparse.Namespace) -> None:
    """Loggt die URLs, ueber die Services den Stream abgreifen koennen."""
    print("\n[Verteilung] Stream verfuegbar unter (127.0.0.1 -> Laptop-IP im Netz):")
    print(f"  RTSP   : rtsp://127.0.0.1:{args.rtsp_port}/{args.path}")
    print(f"  WebRTC : http://127.0.0.1:{args.webrtc_port}/{args.path}")
    print(f"  SRT    : srt://127.0.0.1:{args.srt_port}?streamid=read:{args.path}")
    print(f"  RTMP   : rtmp://127.0.0.1:{args.rtmp_port}/{args.path}")
    print(f"  HLS    : http://127.0.0.1:{args.hls_port}/{args.path}/index.m3u8")
    print()


# ---------------------------------------------------------------------------
# Orchestrierung / Supervisor
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace, ffmpeg: str, mediamtx: str) -> None:
    config = render_mediamtx_config(args)
    fd, config_path = tempfile.mkstemp(prefix="mediamtx_", suffix=".yml", text=True)
    with os.fdopen(fd, "w") as handle:
        handle.write(config)

    # Bei --print die Ausgabe der Kindprozesse erben, sonst verwerfen.
    child_out = None if args.print_output else subprocess.DEVNULL

    mtx_proc = None
    ff_proc = None
    try:
        print(f"[MediaMTX] Starte Media-Server (Config: {config_path}) ...")
        mtx_proc = subprocess.Popen(
            [mediamtx, config_path], stdout=child_out, stderr=child_out
        )

        if not wait_for_port("127.0.0.1", args.rtsp_port, timeout=10.0):
            print(f"[Fehler] MediaMTX hoert nicht auf RTSP-Port {args.rtsp_port}.")
            return
        print(f"[MediaMTX] Laeuft, RTSP-Port {args.rtsp_port} ist offen.")

        ff_cmd = build_ffmpeg_cmd(args, ffmpeg)
        quelle = "Testbild (lavfi)" if args.test_source else f'Capture-Card "{args.device}"'
        print(f"[FFmpeg] Speise {quelle} ein und pushe nach MediaMTX/{args.path} ...")

        print_consumer_urls(args)
        print("[Info] Beenden mit Strg+C.\n")

        backoff = 1.0
        while True:
            ff_proc = subprocess.Popen(ff_cmd, stdout=child_out, stderr=child_out)
            ff_proc.wait()

            # MediaMTX weg -> Gesamtabbruch.
            if mtx_proc.poll() is not None:
                print("[MediaMTX] Prozess beendet -> stoppe Verteilung.")
                break

            # FFmpeg weg (z.B. Capture-Card kurz getrennt) -> Neustart mit Backoff.
            print(
                f"[FFmpeg] Beendet (Code {ff_proc.returncode}). "
                f"Neustart in {backoff:.0f}s ..."
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, 10.0)
    finally:
        if ff_proc is not None:
            stop_process(ff_proc)
        if mtx_proc is not None:
            stop_process(mtx_proc)
        try:
            os.remove(config_path)
        except OSError:
            pass


def main() -> None:
    args = parse_args()
    ffmpeg = resolve_binary("ffmpeg", args.ffmpeg)

    if args.list_devices:
        list_devices(ffmpeg)
        return

    if not args.device and not args.test_source:
        print("[Fehler] Bitte --device angeben (oder --list-devices / --test-source).")
        sys.exit(1)

    mediamtx = resolve_binary("mediamtx", args.mediamtx)

    try:
        run(args, ffmpeg, mediamtx)
    except KeyboardInterrupt:
        print("\n[Beendet] Video-Verteilung gestoppt.")


if __name__ == "__main__":
    # Sauberes Beenden auch bei SIGTERM (z.B. in Containern/Diensten).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    main()
