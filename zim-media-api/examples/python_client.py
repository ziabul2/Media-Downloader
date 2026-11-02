"""Minimal Python client. Replace the base URL and key; do not embed production keys in apps."""

import requests

BASE_URL = "https://api.example.com/api/v1"
API_KEY = "YOUR_API_KEY"


def extract(url: str) -> dict:
    response = requests.post(
        f"{BASE_URL}/extract",
        headers={"X-API-Key": API_KEY},
        json={
            "url": url,
            "media_type": "video",
            "preferred_format": "mp4",
            "preferred_quality": "1080p",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    print(extract("https://archive.org/details/BigBuckBunny_124"))
