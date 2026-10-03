"""
bot/mod/ai/attachments/service.py

Modification():

- 建立附件大小、數量、類型與文字上限的單一邊界。
- 支援文字、程式碼、圖片與可選文件 extractor，其餘類型回報明確限制。

本檔案不依賴 Discord，只處理已下載的受限附件。
"""

from __future__ import annotations

import mimetypes
import asyncio
import io
import tarfile
import zipfile
import ast
import hashlib
import wave
import subprocess
import json
import tempfile
import os
import re
import struct
from pathlib import Path
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

DocumentExtractor = Callable[[str, str, bytes], Awaitable[str]]


class AttachmentType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    ARCHIVE = "archive"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class AttachmentSettings:
    max_count: int
    max_bytes_each: int
    max_total_bytes: int
    max_text_chars: int


@dataclass(frozen=True, slots=True)
class AttachmentInput:
    filename: str
    media_type: str
    data: bytes
    size: int


@dataclass(frozen=True, slots=True)
class ParsedAttachment:
    filename: str
    media_type: str
    attachment_type: AttachmentType
    text: str = ""
    data: bytes = b""
    limitation: str = ""


class AttachmentService:
    _DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}
    _ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".7z", ".rar"}
    _MAX_ARCHIVE_ENTRIES = 300
    _CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt", ".swift",
        ".c", ".cpp", ".cc", ".h", ".hpp", ".go", ".rs", ".rb", ".php",
        ".sh", ".bash", ".zsh", ".fish", ".sql", ".html", ".css", ".scss",
        ".r", ".m", ".lua", ".dart",
    }
    _BINARY_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".bin", ".dat", ".iso", ".class", ".jar", ".pyc"}

    def __init__(self, settings: AttachmentSettings, *, document_extractor: DocumentExtractor | None = None) -> None:
        if min(settings.max_count, settings.max_bytes_each, settings.max_total_bytes, settings.max_text_chars) < 1:
            raise ValueError("Attachment settings must be positive")
        self.settings = settings
        self.document_extractor = document_extractor

    def validate_metadata(self, sizes: tuple[int, ...]) -> None:
        """在下載前使用平台提供的大小拒絕明顯超限附件。"""

        if len(sizes) > self.settings.max_count:
            raise ValueError("attachment count exceeds limit")
        if any(size < 0 or size > self.settings.max_bytes_each for size in sizes):
            raise ValueError("attachment size exceeds limit")
        if sum(sizes) > self.settings.max_total_bytes:
            raise ValueError("total attachment size exceeds limit")

    async def process(self, attachments: tuple[AttachmentInput, ...]) -> tuple[ParsedAttachment, ...]:
        self.validate_metadata(tuple(item.size for item in attachments))
        actual_total = sum(len(item.data) for item in attachments)
        declared_total = sum(item.size for item in attachments)
        if max(actual_total, declared_total) > self.settings.max_total_bytes:
            raise ValueError("total attachment size exceeds limit")
        if any(len(item.data) > self.settings.max_bytes_each for item in attachments):
            raise ValueError("attachment size exceeds limit")
        return tuple([await self._parse(item) for item in attachments])

    async def _parse(self, item: AttachmentInput) -> ParsedAttachment:
        media_type = item.media_type.strip().lower() or mimetypes.guess_type(item.filename)[0] or "application/octet-stream"
        suffix = "." + item.filename.rsplit(".", 1)[-1].lower() if "." in item.filename else ""
        if media_type.startswith("text/") or suffix in self._CODE_EXTENSIONS | {".json", ".md", ".yaml", ".yml", ".toml", ".csv"}:
            text = item.data.decode("utf-8", errors="replace")[: self.settings.max_text_chars]
            if suffix in self._CODE_EXTENSIONS:
                text = self._code_summary(suffix, text)
            return ParsedAttachment(item.filename, media_type, AttachmentType.TEXT, text=text)
        if media_type.startswith("image/"):
            return ParsedAttachment(
                item.filename,
                media_type,
                AttachmentType.IMAGE,
                text=self._image_metadata(suffix, item.data),
                data=item.data,
            )
        if suffix in self._DOCUMENT_EXTENSIONS:
            if self.document_extractor is None:
                return ParsedAttachment(item.filename, media_type, AttachmentType.DOCUMENT, limitation="document parser is not installed")
            try:
                text = (await self.document_extractor(item.filename, media_type, item.data))[: self.settings.max_text_chars]
            except ImportError:
                return ParsedAttachment(item.filename, media_type, AttachmentType.DOCUMENT, limitation="document parser is not installed")
            return ParsedAttachment(item.filename, media_type, AttachmentType.DOCUMENT, text=text)
        if media_type.startswith("audio/"):
            return ParsedAttachment(item.filename, media_type, AttachmentType.AUDIO, text=self._audio_metadata(suffix, item.data), data=item.data)
        if media_type.startswith("video/"):
            metadata = await asyncio.to_thread(
                self._video_metadata,
                suffix,
                item.data,
            )
            return ParsedAttachment(
                item.filename,
                media_type,
                AttachmentType.VIDEO,
                text=metadata,
                data=item.data,
            )
        if suffix in self._ARCHIVE_EXTENSIONS:
            return ParsedAttachment(
                item.filename,
                media_type,
                AttachmentType.ARCHIVE,
                text=self._archive_manifest(item.filename, item.data),
            )
        if suffix in self._BINARY_EXTENSIONS:
            return ParsedAttachment(
                item.filename,
                media_type,
                AttachmentType.UNSUPPORTED,
                text=self._binary_metadata(item.data),
                limitation="binary content is not executed or supplied to the model",
            )
        return ParsedAttachment(item.filename, media_type, AttachmentType.UNSUPPORTED, limitation="unsupported attachment type")

    def _archive_manifest(self, filename: str, data: bytes) -> str:
        """Describe archive entries without extracting any file content."""

        try:
            if zipfile.is_zipfile(io.BytesIO(data)):
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    entries = [info.filename for info in archive.infolist() if not info.is_dir()]
            elif tarfile.is_tarfile(io.BytesIO(data)):
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                    entries = [member.name for member in archive.getmembers() if member.isfile()]
            elif filename.casefold().endswith(".gz"):
                compressed_name = filename[:-3].rstrip(".") or "compressed payload"
                return f"Gzip archive (not extracted):\n{compressed_name}"
            else:
                return "Archive received; its entries were not read because the format is unsupported."
        except (OSError, tarfile.TarError, zipfile.BadZipFile):
            return "Archive received; its entries could not be read safely."
        shown = entries[:self._MAX_ARCHIVE_ENTRIES]
        suffix = "" if len(entries) <= len(shown) else f"\n… {len(entries) - len(shown)} more entries omitted"
        return "Archive manifest (not extracted):\n" + "\n".join(shown) + suffix

    @staticmethod
    def _code_summary(suffix: str, text: str) -> str:
        language = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".jsx": "React JSX", ".tsx": "React TSX",
            ".java": "Java", ".kt": "Kotlin", ".swift": "Swift", ".c": "C", ".cpp": "C++", ".cc": "C++",
            ".h": "C/C++ Header", ".hpp": "C++ Header", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
            ".sh": "Shell", ".bash": "Bash", ".zsh": "Zsh", ".fish": "Fish", ".sql": "SQL", ".html": "HTML",
            ".css": "CSS", ".scss": "SCSS", ".r": "R", ".m": "MATLAB/Objective-C", ".lua": "Lua", ".dart": "Dart",
        }.get(suffix, suffix.lstrip(".").upper())
        if suffix != ".py":
            imports, classes, functions = AttachmentService._generic_code_structure(suffix, text)
            lines = [f"Language: {language}"]
            if imports:
                lines.append("Imports: " + ", ".join(imports[:20]))
            if classes:
                lines.append("Classes: " + ", ".join(classes[:20]))
            if functions:
                lines.append("Functions: " + ", ".join(functions[:20]))
            return "\n".join(lines) + "\n\n" + text
        try:
            tree = ast.parse(text)
            imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
            classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        except SyntaxError:
            return f"Language: {language}\n\n{text}"
        lines = [f"Language: {language}"]
        if imports:
            lines.append("Imports: " + ", ".join(dict.fromkeys(imports[:20])))
        if classes:
            lines.append("Classes: " + ", ".join(classes[:20]))
        if functions:
            lines.append("Functions: " + ", ".join(functions[:20]))
        return "\n".join(lines) + "\n\n" + text

    @staticmethod
    def _generic_code_structure(suffix: str, text: str) -> tuple[list[str], list[str], list[str]]:
        import_patterns = {
            ".js": r"(?:import\s+.*?from\s+['\"](.+?)['\"]|require\(['\"](.+?)['\"]\))",
            ".ts": r"(?:import\s+.*?from\s+['\"](.+?)['\"]|require\(['\"](.+?)['\"]\))",
            ".jsx": r"import\s+.*?from\s+['\"](.+?)['\"]",
            ".tsx": r"import\s+.*?from\s+['\"](.+?)['\"]",
            ".java": r"import\s+([\w.]+)\s*;",
            ".go": r'import\s+"([\w./]+)"',
            ".rs": r"use\s+([\w:]+)",
            ".rb": r"require\s+['\"](.+?)['\"]",
            ".php": r"(?:use|require|include)\s+['\"]?(.+?)['\"]?\s*[;)]",
        }
        imports: list[str] = []
        pattern = import_patterns.get(suffix)
        if pattern:
            for match in re.finditer(pattern, text):
                value = next((group for group in match.groups() if group), "")
                if value:
                    imports.append(value)
        classes = re.findall(r"(?:^|\s)class\s+(\w+)", text, re.MULTILINE)
        functions = re.findall(r"(?:^|\s)(?:function|def|func|fn|sub|method)\s+(\w+)", text, re.MULTILINE)
        return list(dict.fromkeys(imports)), list(dict.fromkeys(classes)), list(dict.fromkeys(functions))

    @staticmethod
    def _binary_metadata(data: bytes) -> str:
        signatures = ((b"MZ", "Windows PE executable"), (b"\x7fELF", "Linux ELF binary"), (b"SQLite format 3", "SQLite database"), (b"\x00asm", "WebAssembly binary"))
        kind = next((label for prefix, label in signatures if data.startswith(prefix)), "unrecognized binary")
        return f"Binary type: {kind}\nSize: {len(data)} bytes\nSHA-256: {hashlib.sha256(data).hexdigest()}"

    @staticmethod
    def _image_metadata(suffix: str, data: bytes) -> str:
        """Read dimensions from common formats without decoding untrusted pixels."""

        try:
            if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
                width, height = struct.unpack(">II", data[16:24])
                return f"Image format: PNG\nDimensions: {width}x{height}\nSize: {len(data)} bytes"
            if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
                width, height = struct.unpack("<HH", data[6:10])
                return f"Image format: GIF\nDimensions: {width}x{height}\nSize: {len(data)} bytes"
        except struct.error:
            return f"Image format: {suffix.lstrip('.').upper() or 'unknown'}\nSize: {len(data)} bytes"
        return f"Image format: {suffix.lstrip('.').upper() or 'unknown'}\nSize: {len(data)} bytes"

    @staticmethod
    def _audio_metadata(suffix: str, data: bytes) -> str:
        if suffix != ".wav":
            return f"Audio format: {suffix.lstrip('.').upper() or 'unknown'}\nSize: {len(data)} bytes"
        try:
            with wave.open(io.BytesIO(data), "rb") as audio:
                frames = audio.getnframes()
                rate = audio.getframerate()
                duration = frames / rate if rate else 0.0
                return f"Audio format: WAV\nDuration: {duration:.2f}s\nSample rate: {rate} Hz\nChannels: {audio.getnchannels()}"
        except (wave.Error, EOFError):
            return "Audio format: WAV\nMetadata could not be read safely."

    @staticmethod
    def _video_metadata(suffix: str, data: bytes) -> str:
        descriptor, name = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height", "-of", "json", name], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode != 0:
                return f"Video format: {suffix.lstrip('.').upper()}\nMetadata unavailable."
            info = json.loads(result.stdout)
            lines = [f"Video format: {suffix.lstrip('.').upper()}"]
            duration = info.get("format", {}).get("duration")
            if duration is not None:
                lines.append(f"Duration: {float(duration):.2f}s")
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video":
                    lines.append(f"Video: {stream.get('codec_name', 'unknown')} {stream.get('width', 0)}x{stream.get('height', 0)}")
            return "\n".join(lines)
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
            return f"Video format: {suffix.lstrip('.').upper()}\nMetadata unavailable."
        finally:
            Path(name).unlink(missing_ok=True)
