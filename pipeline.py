"""
CloudVault pipeline v0: folder-based image upload/download through Discord.

Flow:
  upload:   read file -> hash -> skip if hash already in manifest ->
            generate key -> encrypt -> backend.put() -> save manifest
  download: manifest.get() -> backend.get() -> decrypt -> write file

Drop files in UPLOAD_DIR and run `sync` -- each new file (by content hash)
gets uploaded once; re-running is safe and won't re-upload duplicates.
"""

import hashlib
import time
import uuid
from pathlib import Path

from discord import DiscordBackend
from crypto import generate_file_key, encrypt, decrypt
from manifest import Manifest, FileRecord

UPLOAD_DIR = Path(r"C:\Users\rtani\Desktop\Coading\Data vault\cloudvault\uploads")
DOWNLOAD_DIR = Path(r"C:\Users\rtani\Desktop\Coading\Data vault\cloudvault\downloads")


def _hash_file(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class CloudVault:
    def __init__(self, backend=None, manifest: Manifest | None = None):
        self.backend = backend or DiscordBackend()
        self.manifest = manifest or Manifest()
        UPLOAD_DIR.mkdir(exist_ok=True)
        DOWNLOAD_DIR.mkdir(exist_ok=True)

    # def upload(self, filepath: str) -> str:
    #     path = Path(filepath)
    #     data = path.read_bytes()
    #     content_hash = _hash_file(data)

    #     existing = self.manifest.find_by_hash(content_hash)
    #     if existing:
    #         print(f"Skipped {path.name} -- identical content already uploaded "
    #               f"as {existing.filename} (file_id={existing.file_id})")
    #         return existing.file_id

    #     key = generate_file_key()
    #     encrypted = encrypt(data, key)

    #     file_id = str(uuid.uuid4())
    #     ref = self.backend.put(chunk_id=file_id, data=encrypted)

    #     self.manifest.save(
    #         FileRecord(
    #             file_id=file_id,
    #             filename=path.name,
    #             size_bytes=len(data),
    #             content_hash=content_hash,
    #             key=key,
    #             ref=ref,
    #             created_at=time.time(),
    #         )
    #     )
    #     print(f"Uploaded {path.name} -> file_id={file_id} ({len(data)} bytes)")
    #     return file_id
    def upload(self, filepath: str) -> str:
        path = Path(filepath)
        return self.upload_bytes(path.name, path.read_bytes())

    def upload_bytes(self, filename: str, data: bytes) -> str:
        """Core upload logic, usable with in-memory bytes (e.g. from a UI upload
        widget) as well as from upload(), which reads bytes off disk first."""
        content_hash = _hash_file(data)

        existing = self.manifest.find_by_hash(content_hash)
        if existing:
            print(f"Skipped {filename} -- identical content already uploaded "
                  f"as {existing.filename} (file_id={existing.file_id})")
            return existing.file_id

        key = generate_file_key()
        encrypted = encrypt(data, key)

        file_id = str(uuid.uuid4())
        ref = self.backend.put(chunk_id=file_id, data=encrypted)

        self.manifest.save(
            FileRecord(
                file_id=file_id,
                filename=filename,
                size_bytes=len(data),
                content_hash=content_hash,
                key=key,
                ref=ref,
                created_at=time.time(),
            )
        )
        print(f"Uploaded {filename} -> file_id={file_id} ({len(data)} bytes)")
        return file_id
    def sync_folder(self, folder: Path = UPLOAD_DIR) -> None:
        """Iterate every file in the uploads folder and upload new ones."""
        files = [f for f in folder.iterdir() if f.is_file()]
        if not files:
            print(f"No files found in {folder}/")
            return
        print(f"Found {len(files)} file(s) in {folder}/")
        for f in files:
            self.upload(str(f))

    def download(self, file_id: str, out_path: str | None = None) -> None:
        record = self.manifest.get(file_id)
        encrypted = self.backend.get(record.ref)
        data = decrypt(encrypted, record.key)
        target = Path(out_path) if out_path else DOWNLOAD_DIR / record.filename
        target.write_bytes(data)
        print(f"Downloaded {record.filename} -> {target} ({len(data)} bytes)")

    # def download_all(self) -> None:
    #     """Fetch every file in the manifest into the downloads folder."""
    #     rows = self.manifest.list_files()
    #     if not rows:
    #         print("Manifest is empty -- nothing to download")
    #         return
    #     for file_id, filename, size, created_at in rows:
    #         self.download(file_id)
    def download(self, file_id: str, out_path: str | None = None) -> None:
        data = self.get_bytes(file_id)
        record = self.manifest.get(file_id)
        target = Path(out_path) if out_path else DOWNLOAD_DIR / record.filename
        target.write_bytes(data)
        print(f"Downloaded {record.filename} -> {target} ({len(data)} bytes)")

    def get_bytes(self, file_id: str) -> bytes:
        """Fetch + decrypt a file into memory without writing to disk."""
        record = self.manifest.get(file_id)
        encrypted = self.backend.get(record.ref)
        return decrypt(encrypted, record.key)

    def check_missing(self) -> list[tuple[str, str]]:
        """Non-interactive check: returns [(file_id, filename), ...] for entries
        no longer retrievable from Discord. Used by both the CLI and the UI."""
        rows = self.manifest.list_files()
        missing = []
        for file_id, filename, size, created_at in rows:
            record = self.manifest.get(file_id)
            if not self.backend.exists(record.ref):
                missing.append((file_id, filename))
        return missing

    def prune_ids(self, file_ids: list[str]) -> None:
        for file_id in file_ids:
            self.manifest.delete(file_id)
    # def verify(self, prune: bool = False, assume_yes: bool = False) -> None:
    #     """Check every manifest entry still exists on Discord (not manually deleted).

    #     If any are missing, asks y/n before removing them from the manifest
    #     (this discards that file's encryption key, so only confirm once you're
    #     sure the Discord message is really gone for good).

    #     prune=True / assume_yes=True skip the prompt (for scripts/automation).
    #     """
    #     rows = self.manifest.list_files()
    #     if not rows:
    #         print("Manifest is empty -- nothing to verify")
    #         return
    #     missing = []
    #     for file_id, filename, size, created_at in rows:
    #         record = self.manifest.get(file_id)
    #         ok = self.backend.exists(record.ref)
    #         status = "OK" if ok else "MISSING"
    #         print(f"{status:8s} {file_id}  {filename}")
    #         if not ok:
    #             missing.append((file_id, filename))
    #     print(f"\n{len(rows) - len(missing)}/{len(rows)} files confirmed on Discord")
    #     if not missing:
    #         return

    #     print("Missing (likely deleted from the Discord channel manually):")
    #     for file_id, filename in missing:
    #         print(f"  - {filename} ({file_id})")

    #     do_prune = prune or assume_yes
    #     if not do_prune:
    #         answer = input(f"\nRemove these {len(missing)} entries from the manifest? [y/N] ").strip().lower()
    #         do_prune = answer in ("y", "yes")

    #     if do_prune:
    #         for file_id, filename in missing:
    #             self.manifest.delete(file_id)
    #         print(f"Pruned {len(missing)} entr{'y' if len(missing) == 1 else 'ies'} from the manifest")
    #     else:
    #         print("Left manifest unchanged")
    def verify(self, prune: bool = False, assume_yes: bool = False) -> None:
        """Check every manifest entry still exists on Discord (not manually deleted).

        If any are missing, asks y/n before removing them from the manifest
        (this discards that file's encryption key, so only confirm once you're
        sure the Discord message is really gone for good).

        prune=True / assume_yes=True skip the prompt (for scripts/automation).
        """
        rows = self.manifest.list_files()
        if not rows:
            print("Manifest is empty -- nothing to verify")
            return
        missing = self.check_missing()
        missing_ids = {file_id for file_id, _ in missing}
        for file_id, filename, size, created_at in rows:
            status = "MISSING" if file_id in missing_ids else "OK"
            print(f"{status:8s} {file_id}  {filename}")
        print(f"\n{len(rows) - len(missing)}/{len(rows)} files confirmed on Discord")
        if not missing:
            return

        print("Missing (likely deleted from the Discord channel manually):")
        for file_id, filename in missing:
            print(f"  - {filename} ({file_id})")

        do_prune = prune or assume_yes
        if not do_prune:
            answer = input(f"\nRemove these {len(missing)} entries from the manifest? [y/N] ").strip().lower()
            do_prune = answer in ("y", "yes")

        if do_prune:
            self.prune_ids([file_id for file_id, _ in missing])
            print(f"Pruned {len(missing)} entr{'y' if len(missing) == 1 else 'ies'} from the manifest")
        else:
            print("Left manifest unchanged")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CloudVault CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload")
    up.add_argument("filepath")

    sub.add_parser("sync", help=f"Upload every new file in {UPLOAD_DIR}/")

    down = sub.add_parser("download")
    down.add_argument("file_id")
    down.add_argument("out_path", nargs="?", default=None)

    sub.add_parser("download-all", help=f"Fetch every manifest entry into {DOWNLOAD_DIR}/")
    # sub.add_parser("verify", help="Check every manifest entry still exists on Discord")
    verify_p = sub.add_parser("verify", help="Check every manifest entry still exists on Discord")
    verify_p.add_argument("--prune", action="store_true",
                           help="Delete manifest rows for missing entries without prompting")
    verify_p.add_argument("--yes", action="store_true",
                           help="Same as --prune (skip the y/n confirmation)")
    ls = sub.add_parser("list")

    args = parser.parse_args()
    vault = CloudVault()

    if args.cmd == "upload":
        vault.upload(args.filepath)
    elif args.cmd == "sync":
        vault.sync_folder()
    elif args.cmd == "download":
        vault.download(args.file_id, args.out_path)
    elif args.cmd == "download-all":
        vault.download_all()
    elif args.cmd == "list":
        for file_id, filename, size, created_at in vault.manifest.list_files():
            print(f"{file_id}  {filename:30s}  {size:>8} bytes")
    elif args.cmd == "verify":
        vault.verify(prune=args.prune, assume_yes=args.yes)