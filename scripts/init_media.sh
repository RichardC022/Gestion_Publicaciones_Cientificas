#!/usr/bin/env bash
set -euo pipefail

umask 0027

MEDIA_ROOT="${MEDIA_ROOT:-/data/media}"
MEDIA_GROUP="${MEDIA_GROUP:-media}"

if [[ ! -d "${MEDIA_ROOT}" ]]; then
  printf 'ERROR: MEDIA_ROOT no existe: %s\n' "${MEDIA_ROOT}" >&2
  exit 1
fi

if ! [[ -w "${MEDIA_ROOT}" ]]; then
  printf 'ERROR: MEDIA_ROOT no es escribible por el usuario actual: %s\n' "${MEDIA_ROOT}" >&2
  exit 1
fi

if ! id --groups --name | grep --quiet --word-regexp "${MEDIA_GROUP}"; then
  printf 'ERROR: el usuario actual no pertenece al grupo %s\n' "${MEDIA_GROUP}" >&2
  exit 1
fi

chgrp "${MEDIA_GROUP}" "${MEDIA_ROOT}"
chmod 0750 "${MEDIA_ROOT}"

directories=(
  "${MEDIA_ROOT}/private/drafts"
  "${MEDIA_ROOT}/private/manuscripts"
  "${MEDIA_ROOT}/public/catalog"
  "${MEDIA_ROOT}/tmp/uploads"
)

for directory in "${directories[@]}"; do
  install --directory --mode 0750 "${directory}"
  chgrp "${MEDIA_GROUP}" "${directory}"
  chmod 0750 "${directory}"
done

find "${MEDIA_ROOT}" -type d -exec chmod 0750 {} +
find "${MEDIA_ROOT}" -type f -exec chmod 0640 {} +

printf 'Media volume initialized at %s\n' "${MEDIA_ROOT}"
