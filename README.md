# nas-homelab

Configuration-as-code for a UGREEN NAS media + downloads setup.

- **`PLAN.md`** — the roadmap, decisions, and current state. Start here.
- **`docker/`** — docker-compose stacks (media stack, download stack). *(created as we go)*
- **`notes/`** — inventory notes, how-tos, and runbooks. *(created as we go)*

## Principles

1. Every config is reviewed here on the PC before it reaches the NAS.
2. Secrets never go in git (see `.gitignore`). PIA and other credentials are supplied
   directly on the NAS via `.env` files that stay out of version control.
3. qBittorrent has **no** network path to the internet except through the PIA VPN tunnel.
