# Android integration

Use the REST contract. Do not parse media bytes out of the JSON API.

1. Call `POST /api/v1/extract` with OkHttp or Retrofit and the `X-API-Key` header.
2. Show the returned formats. If `requires_merge` is true, do not present that row as a finished file.
3. If `selection.conversion_required` is true, the file is not MP3. Convert on device or tell the user.
4. Call `POST /api/v1/download-link`.
5. When `delivery` is `direct`, hand `data.url` to `DownloadManager` together with any `required_headers`. A URL that needs a Referer will fail if those headers are dropped.
6. When `delivery` is `redirect`, enqueue `data.download_url`. ZIM responds with `302` and `Cache-Control: no-store`. DownloadManager follows the redirect. The upstream host controls the final filename.
7. Store the file with MediaStore. Do not keep the API key in the app binary; fetch it from your own backend or use a restricted key.

Proxy delivery is off unless the server operator enabled it. Do not build a second proxy in the app to dodge a refusal.

Out of scope: DRM, login cookies, paywalled items, and playlist expansion.
