# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Etapa 1: compilación de producción de la SPA Angular con Node.
# No requiere Node ni npm en la máquina host: todo se compila aquí dentro.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Dependencias con la versión exacta del lockfile (capa cacheable).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Código fuente y build de producción (outputHashing=all, sin sourceMaps).
COPY frontend/ ./
RUN npm run build -- --configuration production

# ---------------------------------------------------------------------------
# Etapa 2: Nginx sirve la SPA compilada, nunca el servidor de desarrollo.
# La configuración se hornea en la imagen; los certificados TLS se montan
# en tiempo de ejecución y jamás se copian al construir.
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf

# SPA compilada publicada en la ruta que sirve `location /`
# (`try_files` resuelve las rutas profundas hacia index.html).
COPY --from=build /app/dist/gpc-frontend/browser /usr/share/nginx/html
