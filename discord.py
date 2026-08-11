"""
Discord-as-storage backend, using a channel webhook (no bot app needed).

Setup:
  1. In Discord: Server Settings -> Integrations -> Webhooks -> New Webhook
  2. Pick the channel you want to use as your "storage bucket"
  3. Copy the webhook URL, put it in DISCORD_WEBHOOK_URL below (or env var)

Notes / limits:
  - 10 MB per attachment on a normal (non-boosted) server.
  - The CDN URL Discord returns is signed and expires. We never store
    that URL directly -- we store (webhook_url, message_id) and re-fetch
    the message before every download to get a fresh URL.
  - Deleting the webhook in Discord invalidates every ref that used it.
"""

import os
import httpx

from base import StorageBackend, StoredRef

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1536799481620733972/ahoxTG_WnWyoUDyallWItoqfjMX1OKd-OgG6JPp_foNYJwKOL8EEG1Km9lDiPKnsGCBN"


class DiscordBackend(StorageBackend):
    def __init__(self, webhook_url: str = DISCORD_WEBHOOK_URL):
        if not webhook_url:
            raise ValueError(
                "No Discord webhook URL set. Export DISCORD_WEBHOOK_URL "
                "or pass webhook_url= explicitly."
            )
        self.webhook_url = webhook_url

    def put(self, chunk_id: str, data: bytes) -> StoredRef:
        if len(data) > 10 * 1024 * 1024:
            raise ValueError(
                f"chunk {chunk_id} is {len(data)} bytes -- over Discord's "
                "10 MB attachment limit. Reduce chunk size."
            )
        files = {"file": (f"{chunk_id}.bin", data, "application/octet-stream")}
        # ?wait=true makes Discord return the message object (with its id)
        # instead of a 204 with no body.
        resp = httpx.post(f"{self.webhook_url}?wait=true", files=files, timeout=30)
        resp.raise_for_status()
        message = resp.json()
        return StoredRef(
            backend="discord",
            data={"message_id": message["id"], "chunk_id": chunk_id},
        )

    def get(self, ref: StoredRef) -> bytes:
        message_id = ref.data["message_id"]
        # Re-fetch the message to get a fresh, unexpired attachment URL.
        resp = httpx.get(f"{self.webhook_url}/messages/{message_id}", timeout=30)
        resp.raise_for_status()
        message = resp.json()
        attachment_url = message["attachments"][0]["url"]

        file_resp = httpx.get(attachment_url, timeout=60)
        file_resp.raise_for_status()
        return file_resp.content

    def delete(self, ref: StoredRef) -> None:
        message_id = ref.data["message_id"]
        resp = httpx.delete(f"{self.webhook_url}/messages/{message_id}", timeout=30)
        # 404 just means it's already gone -- treat as success.
        if resp.status_code not in (204, 404):
            resp.raise_for_status()

    def exists(self, ref: StoredRef) -> bool:
        message_id = ref.data["message_id"]
        resp = httpx.get(f"{self.webhook_url}/messages/{message_id}", timeout=30)
        return resp.status_code == 200