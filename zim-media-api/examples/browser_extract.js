async function extract(url, apiKey) {
  const response = await fetch("https://api.example.com/api/v1/extract", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify({
      url,
      media_type: "video",
      preferred_format: "mp4",
    }),
  });
  if (!response.ok) {
    throw new Error(`Extraction failed: ${response.status}`);
  }
  return response.json();
}

// Use a normal link or location assignment for the ticket redirect.
// Do not fetch the media into a blob. Cross-origin byte access needs source CORS,
// which most hosts do not grant.
export { extract };
