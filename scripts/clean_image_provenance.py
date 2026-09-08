#!/usr/bin/env python3
"""Batch-remove image provenance metadata without pixel re-encoding."""

from __future__ import annotations

import argparse
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".heic", ".heif", ".avif"}
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".cache",
    ".venv",
    "venv",
}
VERIFY_MARKERS = (
    "c2pa",
    "contentauth",
    "content credentials",
    "openai",
    "gpt-image",
    "trainedalgorithmicmedia",
    "algorithmicmedia",
    "prompt",
    "jumbf",
    "jumd",
)
COMMON_MAGIC = {
    ".jpg": ("jpeg",),
    ".jpeg": ("jpeg",),
    ".png": ("png",),
    ".webp": ("webp",),
    ".tif": ("tiff",),
    ".tiff": ("tiff",),
}


@dataclass
class BatchResult:
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    messages: list[str] | None = None
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.messages is None:
            self.messages = []
        if self.errors is None:
            self.errors = []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove C2PA/AI provenance and common image metadata in place."
    )
    parser.add_argument("paths", nargs="+", help="Image files or directories to clean.")
    parser.add_argument("--dry-run", action="store_true", help="List files without changing them.")
    parser.add_argument("--backup", action="store_true", help="Keep exiftool *_original backups.")
    parser.add_argument(
        "--drop-color-profile",
        action="store_true",
        help="Also remove ICC color profiles. By default ICC profiles are preserved.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-clean scan for C2PA/OpenAI/provenance markers.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100,
        help="Number of files per exiftool invocation.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=5,
        help="Number of exiftool batches to run concurrently (default: 5).",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Append progress, warnings, and errors to this log file.",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Start a detached cleanup job and return immediately. Writes to --log-file or a timestamped log.",
    )
    parser.add_argument(
        "--skip-mismatched-magic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip common files whose extension disagrees with their file header.",
    )
    return parser.parse_args()


def find_images(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.exists():
            print(f"[missing] {path}", file=sys.stderr)
            continue
        if path.is_file():
            if path.suffix.lower() in IMAGE_EXTS:
                found.append(path)
            continue
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for name in files:
                file_path = Path(root) / name
                if file_path.suffix.lower() in IMAGE_EXTS:
                    found.append(file_path)
    return sorted(dict.fromkeys(p.resolve() for p in found))


def require_exiftool() -> str:
    exiftool = shutil.which("exiftool")
    if not exiftool:
        raise SystemExit("ExifTool is required. Install it and rerun this command.")
    return exiftool


def chunks(items: list[Path], size: int) -> list[list[Path]]:
    return [items[i : i + max(1, size)] for i in range(0, len(items), max(1, size))]


def emit(message: str, log_file: Path | None = None, *, stream=sys.stdout) -> None:
    print(message, file=stream, flush=True)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")


def sniff_kind(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return None
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    return None


def split_mismatched_magic(files: list[Path]) -> tuple[list[Path], list[Path]]:
    valid: list[Path] = []
    skipped: list[Path] = []
    for path in files:
        expected = COMMON_MAGIC.get(path.suffix.lower())
        actual = sniff_kind(path) if expected else None
        if expected and actual and actual not in expected:
            skipped.append(path)
        else:
            valid.append(path)
    return valid, skipped


def run_exiftool_with_files(exiftool: str, args: list[str], files: list[Path]) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        argfile = Path(handle.name)
        for item in args:
            handle.write(item + "\n")
        for path in files:
            handle.write(str(path) + "\n")
    try:
        return subprocess.run([exiftool, "-@", str(argfile)], text=True, capture_output=True)
    finally:
        try:
            argfile.unlink()
        except OSError:
            pass


def clean_group(exiftool: str, args: list[str], group: list[Path]) -> BatchResult:
    proc = run_exiftool_with_files(exiftool, args, group)
    if proc.returncode == 0:
        return BatchResult(ok=len(group), messages=[proc.stdout.strip()] if proc.stdout.strip() else [])

    result = BatchResult()
    if len(group) == 1:
        return BatchResult(failed=1, errors=[proc.stderr.strip() or proc.stdout.strip()])

    # Isolate bad files without treating the whole batch as failed.
    for path in group:
        single = run_exiftool_with_files(exiftool, args, [path])
        if single.returncode == 0:
            result.ok += 1
            if single.stdout.strip():
                result.messages.append(single.stdout.strip())
        else:
            result.failed += 1
            result.errors.append(f"{path}: {single.stderr.strip() or single.stdout.strip()}")
    return result


def clean_files(
    exiftool: str,
    files: list[Path],
    keep_backup: bool,
    chunk_size: int,
    preserve_color_profile: bool,
    jobs: int,
    log_file: Path | None,
) -> int:
    result = BatchResult()
    overwrite_flags = [] if keep_backup else ["-overwrite_original"]
    # Remove all embedded metadata groups. ExifTool edits metadata containers without
    # decoding/re-encoding image pixels for supported formats.
    preserve_flags = ["--icc_profile:all"] if preserve_color_profile else []
    base_args = [
        "-P",
        *overwrite_flags,
        "-all=",
        *preserve_flags,
    ]
    groups = chunks(files, chunk_size)
    total = len(groups)
    done = 0
    workers = max(1, jobs)
    if workers == 1:
        for group in groups:
            batch = clean_group(exiftool, base_args, group)
            result.ok += batch.ok
            result.failed += batch.failed
            result.skipped += batch.skipped
            done += 1
            for line in batch.messages or []:
                emit(line, log_file)
            for line in batch.errors or []:
                emit(line, log_file, stream=sys.stderr)
            emit(f"[clean] batch {done}/{total}: ok={result.ok} failed={result.failed}", log_file)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(clean_group, exiftool, base_args, group) for group in groups]
            for future in as_completed(futures):
                batch = future.result()
                result.ok += batch.ok
                result.failed += batch.failed
                result.skipped += batch.skipped
                done += 1
                for line in batch.messages or []:
                    emit(line, log_file)
                for line in batch.errors or []:
                    emit(line, log_file, stream=sys.stderr)
                emit(f"[clean] batch {done}/{total}: ok={result.ok} failed={result.failed}", log_file)
    return result.failed


def verify_files(
    exiftool: str,
    files: list[Path],
    chunk_size: int,
    log_file: Path | None,
) -> list[tuple[Path, list[str]]]:
    residual: list[tuple[Path, list[str]]] = []
    groups = chunks(files, chunk_size)
    for index, group in enumerate(groups, start=1):
        proc = run_exiftool_with_files(exiftool, ["-a", "-G1", "-s"], group)
        if proc.returncode != 0:
            emit(proc.stderr.strip(), log_file, stream=sys.stderr)
            raise SystemExit(1)
        current: Path | None = group[0] if len(group) == 1 else None
        hits: list[str] = []
        for line in proc.stdout.splitlines():
            if line.startswith("======== "):
                if current and hits:
                    residual.append((current, hits))
                current = Path(line.removeprefix("======== ").strip())
                hits = []
                continue
            if line.startswith(("[ExifTool]", "[System]", "[File]")):
                continue
            lower = line.lower()
            if any(marker in lower for marker in VERIFY_MARKERS):
                hits.append(line.strip())
        if current and hits:
            residual.append((current, hits))
        emit(f"[verify] batch {index}/{len(groups)}: residual_files={len(residual)}", log_file)
    return residual


def background_args(args: argparse.Namespace) -> tuple[list[str], Path]:
    log_file = args.log_file
    if not log_file:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        log_file = Path.cwd() / f"clean-image-provenance-{stamp}.log"

    command = [sys.executable, str(Path(__file__).resolve())]
    for path in args.paths:
        command.append(path)
    if args.dry_run:
        command.append("--dry-run")
    if args.backup:
        command.append("--backup")
    if args.drop_color_profile:
        command.append("--drop-color-profile")
    if args.no_verify:
        command.append("--no-verify")
    if not args.skip_mismatched_magic:
        command.append("--no-skip-mismatched-magic")
    command.extend(["--chunk-size", str(args.chunk_size)])
    command.extend(["--jobs", str(args.jobs)])
    return command, log_file


def main() -> int:
    args = parse_args()
    if args.background:
        command, log_file = background_args(args)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write("$ " + " ".join(command) + "\n")
            proc = subprocess.Popen(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        # Ready-to-paste monitoring commands. A background run with only a pid
        # and a path is a black box: the caller still has to guess how to watch
        # it, and usually just does not pass anything on to the user.
        quoted_log = shlex.quote(str(log_file))
        print(f"Started background cleanup pid={proc.pid}")
        print(f"stable_log={log_file}")
        print(f"stop_command=kill {proc.pid}")
        print(f"follow_command=tail -F {quoted_log}")
        print(f"status_command=tail -n 20 {quoted_log}")
        return 0

    files = find_images(args.paths)
    emit(f"Found {len(files)} image(s).", args.log_file)
    if not files:
        return 0

    if args.dry_run:
        for path in files:
            emit(str(path), args.log_file)
        return 0

    exiftool = require_exiftool()
    skipped: list[Path] = []
    if args.skip_mismatched_magic:
        files, skipped = split_mismatched_magic(files)
        for path in skipped:
            emit(f"[skip] extension/header mismatch: {path}", args.log_file, stream=sys.stderr)
        emit(f"Processable: {len(files)} image(s). Skipped mismatched: {len(skipped)}.", args.log_file)

    failures = clean_files(
        exiftool,
        files,
        args.backup,
        args.chunk_size,
        preserve_color_profile=not args.drop_color_profile,
        jobs=args.jobs,
        log_file=args.log_file,
    )

    residual: list[tuple[Path, list[str]]] = []
    if not args.no_verify:
        residual = verify_files(exiftool, files, args.chunk_size, args.log_file)

    emit(f"Cleaned: {len(files) - failures}/{len(files)} image(s). Skipped: {len(skipped)}.", args.log_file)
    if residual:
        emit("Residual provenance-like markers found:", args.log_file, stream=sys.stderr)
        for path, hits in residual:
            emit(f"- {path}", args.log_file, stream=sys.stderr)
            for hit in hits[:8]:
                emit(f"  {hit}", args.log_file, stream=sys.stderr)
            if len(hits) > 8:
                emit(f"  ... {len(hits) - 8} more", args.log_file, stream=sys.stderr)
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
