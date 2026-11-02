# Security

ZIM is an extraction and coordination service. It is not an open proxy and it does not bypass access controls.

## Threats that are in scope

- Server-side request forgery through the submitted URL, redirects, or DNS rebinding.
- Leakage of API keys, signed media URLs, cookies, and ticket values into logs or metrics.
- Unbounded extraction or streaming that exhausts CPU, memory, or bandwidth.
- Using proxy mode to reach a host the direct client could not.

## Controls

- Only `http` and `https`. Credentials in the URL are rejected.
- Literal and resolved addresses must be global. Loopback, private, link-local, multicast, reserved, CGNAT, and cloud metadata names are blocked.
- Extractor processes install a socket guard and re-check every connection.
- Redirects during proxying are revalidated. `Set-Cookie` is not forwarded. Client headers are not copied through.
- `trust_env` is off for the proxy client so `HTTP_PROXY` cannot be turned into a tunnel.
- Generic yt-dlp fetching is disabled. `geo_bypass` is off. Cookies and account logins are not accepted.
- API keys are hashed with HMAC-SHA256 and a pepper. The pepper must not be the example value in production.
- Tickets are `secrets.token_urlsafe` values. They are not encoded URLs.
- Logs pass through a redaction formatter. Metrics labels are endpoint, status, and delivery only.
- Proxy streaming, server-side merge, and server-side MP3 conversion default to off.

## Reporting

If you find a way to make the service fetch an internal address or write a secret to a log, stop using that deployment and rotate `API_KEY_PEPPER` plus every API key.
