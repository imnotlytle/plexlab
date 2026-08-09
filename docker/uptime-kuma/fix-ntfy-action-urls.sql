-- Give every non-HTTP monitor a `url`, or its ntfy notifications fail silently.
--
-- ROOT CAUSE (found by deliberately breaking a monitor and checking the topic was empty):
-- Uptime Kuma's ntfy provider attaches a "view" action button to every alert and populates it from
-- `monitorJSON.url` — the monitor's OWN url column, NOT the Primary Base URL setting:
--
--     "actions": [{ "action": "view", "label": "Open " + name, "url": monitorJSON.url }]
--
-- `port` and `dns` monitors never set that column, so the url is null and ntfy rejects the ENTIRE
-- request with HTTP 400 "actions invalid; parameter 'url' is required for action 'view'".
-- The monitor still records DOWN correctly — it just never tells anyone. Setting primaryBaseURL
-- does NOT fix this; the provider does not read it.
--
-- The url is cosmetic for port/dns checks (the check uses hostname+port), so pointing it at each
-- service's own web UI both fixes the notification and makes the button in the alert useful.

UPDATE monitor SET url = 'http://192.168.68.56:8989' WHERE name = 'Sonarr'               AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:7878' WHERE name = 'Radarr'               AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:9696' WHERE name = 'Prowlarr'             AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:6767' WHERE name = 'Bazarr'               AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:8080' WHERE name = 'qBittorrent'          AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:8222' WHERE name = 'Vaultwarden'          AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:3003' WHERE name = 'Homepage'             AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:13378' WHERE name = 'Audiobookshelf (LAN)' AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:8083' WHERE name = 'Calibre-Web (LAN)'    AND (url IS NULL OR url = '');
UPDATE monitor SET url = 'http://192.168.68.56:3000' WHERE name = 'AdGuard DNS resolution' AND (url IS NULL OR url = '');

-- Safety net for anything added later that is not an http monitor.
UPDATE monitor SET url = 'http://192.168.68.56:3001' WHERE (url IS NULL OR url = '');
