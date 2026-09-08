---
name: xxd-strip-ai-meta
description: Remove C2PA Content Credentials, AI provenance, OpenAI/gpt-image metadata, prompts, EXIF/XMP/IPTC/comment/software metadata from image files or directories. Use when users ask to strip "made with AI", C2PA, Content Credentials, image metadata, EXIF, AI labels, OpenAI provenance, or batch-clean many PNG/JPEG/WebP/TIFF images while replacing originals and preserving pixel quality as much as possible.
---

# xxd-strip-ai-meta

## Workflow

Use `scripts/clean_image_provenance.py` for image files or directories. It:

- Recursively finds supported images in directories.
- Accepts one or more local paths in any mix: individual image files, multiple files, directories, multiple directories, or files and directories together. Resolves and deduplicates overlapping inputs.
- Replaces originals by default using `exiftool`.
- Uses bounded chunks and exiftool argument files so large batches do not create huge shell commands.
- Reports per-batch progress and isolates bad files instead of counting a whole batch as failed.
- Skips common files whose extension does not match their header, such as JPEG data saved as `.webp`.
- Avoids image decode/re-encode so JPEG quality and PNG pixels are not recompressed.
- Preserves ICC color profiles by default to reduce visible color shifts.
- Preserves filesystem modification time by default.
- Verifies that C2PA/OpenAI/gpt/prompt/provenance markers are gone.

Run from the skill directory or call the script by absolute path:

```bash
python3 scripts/clean_image_provenance.py /path/to/images
```

Multiple and mixed inputs work in one command:

```bash
python3 scripts/clean_image_provenance.py /path/to/folder-a /path/to/folder-b /path/to/one.png /path/to/two.jpg
```

## Prepare the Environment

Before running the script, check that Python 3 and ExifTool work. If either is missing, inspect the user's actual OS, shell, CPU architecture, permissions, and available package managers, then install and configure the missing tool with the most appropriate native method. On macOS prefer Homebrew; on Windows prefer an available Windows package manager or the official ExifTool distribution; on Linux use the distribution's package manager. Do not assume one fixed command fits every machine.

After installation, verify both tools in the current shell and fix `PATH` or the executable name when needed. Continue the original cleanup automatically. Ask the user only when interactive administrator approval, credentials, or a security choice is genuinely required.

For large directories, prefer a detached background run with a log:

```bash
python3 scripts/clean_image_provenance.py /path/to/images --background
```

`--background` returns immediately and prints its own monitoring commands, already resolved:

```text
Started background cleanup pid=12345
stable_log=/path/to/clean-image-provenance-20260808-100021.log
stop_command=kill 12345
follow_command=tail -F /path/to/clean-image-provenance-20260808-100021.log
status_command=tail -n 20 /path/to/clean-image-provenance-20260808-100021.log
```

**Whenever a background run is started, the final response must pass the stop, follow, and status commands on to the user, copied from that output and in that order.** Do not report only "started in the background" with a pid: a minutes-long job with no log path and no `tail -F` is a black box the user cannot check or cancel. This does not apply to foreground runs, which have already finished by the time you report.

Use a specific log path when needed:

```bash
python3 scripts/clean_image_provenance.py /path/to/images --background --log-file /path/to/clean-image-provenance.log
```

For a dry run:

```bash
python3 scripts/clean_image_provenance.py /path/to/images --dry-run
```

Keep backup sidecars when the user wants reversibility:

```bash
python3 scripts/clean_image_provenance.py /path/to/images --backup
```

For maximum metadata removal, including ICC color profiles:

```bash
python3 scripts/clean_image_provenance.py /path/to/images --drop-color-profile
```

The script defaults to five concurrent ExifTool batches for a practical speed/load balance on modern SSDs, including fast external SSDs:

```bash
python3 scripts/clean_image_provenance.py /path/to/images --jobs 5
```

Use `--jobs 1` when minimum system and disk load matters more than throughput.

## Operating Rules

- State that stripping provenance should be used for privacy, internal processing, or metadata hygiene, not for misrepresenting AI-generated media.
- Describe the capability accurately: it removes supported metadata, but cannot guarantee detection or removal of every platform's closed, pixel-embedded, fingerprint-based, or server-resolved watermark. Never call it a universal AI-watermark remover.
- Prepare missing dependencies intelligently for the user's actual macOS, Windows, or Linux environment, then resume the cleanup. Do not merely print an installation hint and stop when the environment can be configured safely.
- Prefer metadata stripping over full image conversion. Do not use ImageMagick `-strip` unless the user accepts possible color-profile changes or `exiftool` is unavailable.
- Do not rewrite pixels, resize, change format, or recompress images unless the user explicitly requests it.
- Run verification after cleaning unless the user explicitly asks for `--no-verify`. If verification reports residual markers, surface the files and the remaining markers.
- For large directories, do not run the foreground command by default. Use `--background` and tell the user the PID and log path.
- Default to `--jobs 5` for a practical balance on modern SSDs. Reduce to `--jobs 1` when the user explicitly prioritizes minimum system and disk load, or when the drive becomes unstable or unusually slow under concurrent writes.
- If a run is interrupted, rerun the same command; metadata stripping is idempotent.
- If mismatched files are skipped, report the skipped paths from the log. Do not rename or re-encode them unless the user explicitly asks.

## Supported Files

The script targets: `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`, `.heic`, `.heif`, `.avif`.

Unsupported files are skipped. Hidden directories and common dependency/cache directories are ignored.

Remote URLs, cloud-storage links, archives, and path lists supplied through standard input are not accepted directly. Download, extract, or resolve them to local file and directory paths first.
