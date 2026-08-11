"""
CloudVault pipeline v0: single-chunk image upload/download through Discord.

Flow:
  upload:   read file -> generate key -> encrypt -> backend.put() -> save manifest
  download: manifest.get() -> backend.get() -> decrypt -> write file

This intentionally skips chunking/dedup for now since images are under
10 MB -- chunking gets added once we outgrow single-attachment size.
"""

import time
import uuid
from pathlib import Path

from discord import DiscordBackend
from crypto import generate_file_key, encrypt, decrypt
from manifest import Manifest, FileRecord


class CloudVault:
    def __init__(self, backend=None, manifest: Manifest | None = None):
        self.backend = backend or DiscordBackend()
        self.manifest = manifest or Manifest()

    def upload(self, filepath: str) -> str:
        path = Path(filepath)
        data = path.read_bytes()

        key = generate_file_key()
        encrypted = encrypt(data, key)

        file_id = str(uuid.uuid4())
        ref = self.backend.put(chunk_id=file_id, data=encrypted)

        self.manifest.save(
            FileRecord(
                file_id=file_id,
                filename=path.name,
                size_bytes=len(data),
                key=key,
                ref=ref,
                created_at=time.time(),
            )
        )
        print(f"Uploaded {path.name} -> file_id={file_id} ({len(data)} bytes)")
        return file_id

    def download(self, file_id: str, out_path: str) -> None:
        record = self.manifest.get(file_id)
        encrypted = self.backend.get(record.ref)
        data = decrypt(encrypted, record.key)
        Path(out_path).write_bytes(data)
        print(f"Downloaded {record.filename} -> {out_path} ({len(data)} bytes)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CloudVault CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload")
    up.add_argument("filepath")

    down = sub.add_parser("download")
    down.add_argument("file_id")
    down.add_argument("out_path")

    ls = sub.add_parser("list")

    args = parser.parse_args()
    vault = CloudVault()

    if args.cmd == "upload":
        vault.upload(args.filepath)
    elif args.cmd == "download":
        vault.download(args.file_id, args.out_path)
    elif args.cmd == "list":
        for file_id, filename, size, created_at in vault.manifest.list_files():
            print(f"{file_id}  {filename:30s}  {size:>8} bytes")