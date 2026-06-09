FROM python:3.11-slim

WORKDIR /app

# Abhaengigkeiten zuerst installieren (besseres Layer-Caching).
# mavsdk bringt den passenden, statisch gelinkten mavsdk_server fuer Linux mit,
# daher sind keine zusaetzlichen System-Bibliotheken noetig.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Anwendung
COPY telemetry_reader.py echo_server.py ./

# Logs sofort (ungepuffert) ausgeben, damit sie in `docker logs` erscheinen.
ENV PYTHONUNBUFFERED=1

# Die CLI-Parameter bleiben erhalten: alles nach dem Image-Namen wird an
# telemetry_reader.py durchgereicht, z.B.
#   docker run --rm -p 14550:14550/udp mavlinkimport \
#       --http-host host.docker.internal --route /telemetry \
#       --drone-name "Drohne-1" --drone-id 1
ENTRYPOINT ["python", "-u", "telemetry_reader.py"]
