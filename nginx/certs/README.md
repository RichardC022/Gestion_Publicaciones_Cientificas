# Certificados TLS

Coloca aquí los certificados institucionales antes de iniciar `web`.

- Certificado público: `fullchain.pem`
- Clave privada: `privkey.pem`

Para un piloto local sin certificado institucional, puedes generar un certificado autofirmado con:

```bash
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout nginx/certs/privkey.pem \
  -out nginx/certs/fullchain.pem \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Los archivos `.pem`, `.key` y `.crt` no deben versionarse.
