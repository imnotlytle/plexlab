-- Uptime Kuma monitor seed. Applied once, after the admin account exists (user_id 1).
--
-- Uptime Kuma v1 has NO REST API for monitor CRUD (socket.io only), so monitors are either clicked
-- in by hand or inserted here. Run with the container up, then restart it so it reloads them:
--   docker exec -i uptime-kuma sqlite3 /app/data/kuma.db < seed-monitors.sql
--   docker restart uptime-kuma
--
-- Idempotent: every insert is guarded by a NOT EXISTS on the monitor name.
--
-- The public hostnames accept 3xx as healthy — overseerr answers 307 and books answers 302 (both
-- are login redirects, not failures). Using a strict 200-299 there would alert constantly.
--
-- The *arr apps and qBittorrent are TCP port checks rather than HTTP, so they need no API key and
-- do not trip over their login pages.

-- ---------- public hostnames (HTTP, 2xx+3xx ok) ----------
INSERT INTO monitor (name, type, url, user_id, interval, retry_interval, maxretries, timeout, accepted_statuscodes_json, active)
SELECT 'Overseerr (public)', 'http', 'https://overseerr.patplex.net', 1, 300, 60, 2, 48, '["200-299","300-399"]', 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Overseerr (public)');

INSERT INTO monitor (name, type, url, user_id, interval, retry_interval, maxretries, timeout, accepted_statuscodes_json, active)
SELECT 'Audiobookshelf (public)', 'http', 'https://abs.patplex.net', 1, 300, 60, 2, 48, '["200-299","300-399"]', 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Audiobookshelf (public)');

INSERT INTO monitor (name, type, url, user_id, interval, retry_interval, maxretries, timeout, accepted_statuscodes_json, active)
SELECT 'Calibre-Web (public)', 'http', 'https://books.patplex.net', 1, 300, 60, 2, 48, '["200-299","300-399"]', 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Calibre-Web (public)');

INSERT INTO monitor (name, type, url, user_id, interval, retry_interval, maxretries, timeout, accepted_statuscodes_json, active)
SELECT 'Shelfmark (public)', 'http', 'https://shelfmark.patplex.net', 1, 300, 60, 2, 48, '["200-299","300-399"]', 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Shelfmark (public)');

-- ---------- Plex ----------
-- /identity is the one Plex endpoint that answers 200 without a token.
INSERT INTO monitor (name, type, url, user_id, interval, retry_interval, maxretries, timeout, accepted_statuscodes_json, active)
SELECT 'Plex', 'http', 'http://192.168.68.56:32400/identity', 1, 120, 60, 2, 48, '["200-299"]', 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Plex');

-- ---------- LAN services (TCP port) ----------
INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'Sonarr', 'port', '192.168.68.56', 8989, 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Sonarr');

INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'Radarr', 'port', '192.168.68.56', 7878, 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Radarr');

INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'Prowlarr', 'port', '192.168.68.56', 9696, 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Prowlarr');

INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'Bazarr', 'port', '192.168.68.56', 6767, 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Bazarr');

INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'qBittorrent', 'port', '192.168.68.56', 8080, 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'qBittorrent');

INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'Vaultwarden', 'port', '192.168.68.56', 8222, 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Vaultwarden');

INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'Homepage', 'port', '192.168.68.56', 3003, 1, 300, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Homepage');

INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'Audiobookshelf (LAN)', 'port', '192.168.68.56', 13378, 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Audiobookshelf (LAN)');

INSERT INTO monitor (name, type, hostname, port, user_id, interval, retry_interval, maxretries, active)
SELECT 'Calibre-Web (LAN)', 'port', '192.168.68.56', 8083, 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'Calibre-Web (LAN)');

-- ---------- AdGuard DNS ----------
-- This is the one that matters most: if AdGuard's DNS stops answering, every device on the LAN
-- loses name resolution. Resolves a known-good name THROUGH AdGuard rather than just checking :53
-- is open, so a wedged-but-listening resolver is still caught.
INSERT INTO monitor (name, type, hostname, port, dns_resolve_server, dns_resolve_type, user_id, interval, retry_interval, maxretries, active)
SELECT 'AdGuard DNS resolution', 'dns', 'github.com', 53, '192.168.68.56', 'A', 1, 120, 60, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'AdGuard DNS resolution');

INSERT INTO monitor (name, type, url, user_id, interval, retry_interval, maxretries, timeout, accepted_statuscodes_json, active)
SELECT 'AdGuard admin UI', 'http', 'http://192.168.68.56:3000', 1, 300, 60, 2, 48, '["200-299","300-399"]', 1
WHERE NOT EXISTS (SELECT 1 FROM monitor WHERE name = 'AdGuard admin UI');
