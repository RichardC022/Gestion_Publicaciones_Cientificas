#!/usr/bin/env bash
# Genera un certificado AUTOFIRMADO para pruebas y pilotos sin certificado
# institucional (TSK-87). No sobrescribe uno existente: el institucional manda.
#
#   ./scripts/make_dev_cert.sh [directorio]    # por defecto nginx/certs
#
# Los .pem están en .gitignore y no deben versionarse. El navegador mostrará una
# advertencia con este certificado; en producción se reemplaza por el institucional.
set -euo pipefail

DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)/nginx/certs}"

if [ -f "${DIR}/fullchain.pem" ] && [ -f "${DIR}/privkey.pem" ]; then
    echo "Ya existe un certificado en ${DIR}; no se sobrescribe."
    exit 0
fi

mkdir -p "${DIR}"
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "${DIR}/privkey.pem" \
    -out "${DIR}/fullchain.pem" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
chmod 0644 "${DIR}/fullchain.pem"
chmod 0600 "${DIR}/privkey.pem"
echo "Certificado autofirmado creado en ${DIR} (365 días, CN=localhost)."
