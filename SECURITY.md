# Security Policy

## Supported versions

AniFlow is currently in early development. Security fixes are applied to the latest revision only.

## Deployment guidance

AniFlow does not include user authentication. Anyone who can reach the Web interface can create or remove download tasks and may delete files in the configured download directory.

- Bind Uvicorn to `127.0.0.1` and place it behind a reverse proxy.
- Enable HTTPS and access control at the reverse proxy, VPN, or firewall layer.
- Run the service as an unprivileged account with access limited to its data and download directories.
- Do not commit `.env`, databases, torrent state, logs, downloaded media, private keys, or server addresses.
- Keep Python, libtorrent, and all Python dependencies updated.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when it is available for the repository. Include the affected revision, reproduction steps, impact, and any suggested mitigation. Do not publish credentials, private tracker URLs, or personal media paths in a public issue.
