"""Untrusted source bytes become an intermediate document, never Evidence."""

import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from pypdf import PdfReader

PARSER_VERSION = "source-parser/v3"
SUPPORTED_FORMATS = frozenset({"txt", "md", "docx", "pdf"})
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class SourceParseError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class OCRRequired(SourceParseError):
    def __init__(self, page_numbers: list[int]):
        self.page_numbers = page_numbers
        pages = ", ".join(map(str, page_numbers))
        super().__init__("OCR_REQUIRED", f"PDF pages require OCR or blank-page review: {pages}")


@dataclass(frozen=True)
class ParsedPage:
    page_no: int
    text: str
    # DOCX paragraph starts are authoritative; line breaks inside a paragraph are not.
    paragraph_starts: list[int] | None = None


@dataclass(frozen=True)
class ParsedDocument:
    file_format: str
    pages: list[ParsedPage]
    encoding: str | None
    warnings: list[str]
    parser_version: str = PARSER_VERSION

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)

    def to_bytes(self) -> bytes:
        payload = asdict(self)
        payload["text"] = self.text
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def validate_source_file(path: Path, file_format: str) -> None:
    if file_format not in SUPPORTED_FORMATS:
        raise SourceParseError("UNSUPPORTED_FORMAT", f"unsupported import format: {file_format}")
    with path.open("rb") as stream:
        signature = stream.read(8)
    if file_format == "pdf" and not signature.startswith(b"%PDF-"):
        raise SourceParseError("INVALID_FILE", "PDF signature is missing")
    if file_format == "docx":
        if not zipfile.is_zipfile(path):
            raise SourceParseError("INVALID_FILE", "DOCX is not a ZIP package")
        _validate_docx_package(path)
    if file_format in {"txt", "md"} and b"\x00" in signature:
        raise SourceParseError("INVALID_FILE", "plain text contains NUL bytes")


def _validate_docx_package(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 10_000:
                raise SourceParseError("UNSAFE_ARCHIVE", "DOCX contains too many entries")
            total_size = 0
            names: set[str] = set()
            for info in infos:
                name = info.filename.replace("\\", "/")
                parts = name.split("/")
                if name.startswith("/") or ".." in parts or ":" in name:
                    raise SourceParseError("UNSAFE_ARCHIVE", "DOCX contains an unsafe entry path")
                if info.flag_bits & 1:
                    raise SourceParseError("UNSAFE_ARCHIVE", "encrypted DOCX entry is unsupported")
                if info.file_size > 50 * 1024 * 1024:
                    raise SourceParseError("UNSAFE_ARCHIVE", "DOCX entry exceeds size limit")
                if info.file_size > 1024 * 1024 and info.file_size > max(1, info.compress_size) * 200:
                    raise SourceParseError("UNSAFE_ARCHIVE", "DOCX compression ratio is unsafe")
                total_size += info.file_size
                if total_size > 250 * 1024 * 1024:
                    raise SourceParseError("UNSAFE_ARCHIVE", "DOCX uncompressed size exceeds limit")
                names.add(name)
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise SourceParseError("INVALID_FILE", "required DOCX parts are missing")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise SourceParseError("UNSAFE_ARCHIVE", "macro-enabled package is not accepted as DOCX")
    except zipfile.BadZipFile as exc:
        raise SourceParseError("INVALID_FILE", "DOCX package is corrupt") from exc


def _decode_text(data: bytes) -> tuple[str, str, list[str]]:
    if b"\x00" in data:
        raise SourceParseError("INVALID_FILE", "plain text contains NUL bytes")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = data.decode(encoding)
            warning = ["encoding_fallback_gb18030"] if encoding == "gb18030" else []
            return text.replace("\r\n", "\n").replace("\r", "\n"), encoding, warning
        except UnicodeDecodeError:
            continue
    raise SourceParseError("INVALID_ENCODING", "text cannot be decoded as UTF-8 or GB18030")


def parse_source_file(path: Path, file_format: str) -> ParsedDocument:
    validate_source_file(path, file_format)
    if file_format in {"txt", "md"}:
        text, encoding, warnings = _decode_text(path.read_bytes())
        if not text.strip():
            raise SourceParseError("EMPTY_TEXT", "source contains no text")
        return ParsedDocument(file_format, [ParsedPage(1, text)], encoding, warnings)

    if file_format == "docx":
        with zipfile.ZipFile(path) as archive, archive.open("word/document.xml") as document:
            xml_bytes = document.read(50 * 1024 * 1024 + 1)
        if len(xml_bytes) > 50 * 1024 * 1024:
            raise SourceParseError("UNSAFE_ARCHIVE", "DOCX document XML exceeds size limit")
        try:
            root = ElementTree.fromstring(xml_bytes)
        except (ParseError, DefusedXmlException) as exc:
            raise SourceParseError("INVALID_FILE", "DOCX XML is invalid") from exc
        paragraphs = []
        for paragraph in root.iter(f"{{{WORD_NS}}}p"):
            parts = []
            for node in paragraph.iter():
                if node.tag == f"{{{WORD_NS}}}t":
                    parts.append(node.text or "")
                elif node.tag == f"{{{WORD_NS}}}tab":
                    parts.append("\t")
                elif node.tag == f"{{{WORD_NS}}}br":
                    parts.append("\n")
            value = "".join(parts)
            if value.strip():
                paragraphs.append(value)
        if not paragraphs:
            raise SourceParseError("EMPTY_TEXT", "DOCX contains no extractable text")
        starts, line_no = [], 1
        for value in paragraphs:
            starts.append(line_no)
            line_no += len(value.split("\n"))
        return ParsedDocument(file_format, [ParsedPage(1, "\n".join(paragraphs), starts)], None, [])

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise SourceParseError("ENCRYPTED_PDF", "encrypted PDF requires manual handling")
        if len(reader.pages) > 2_000:
            raise SourceParseError("PAGE_LIMIT", "PDF exceeds page limit")
        pages = [ParsedPage(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
    except SourceParseError:
        raise
    except Exception as exc:  # Parser boundary for malformed third-party files.
        raise SourceParseError("INVALID_FILE", "PDF parser could not read this file") from exc
    missing_text_pages = [page.page_no for page in pages if not page.text.strip()]
    if missing_text_pages:
        # A text cover must not make scanned body pages disappear from the corpus.
        # Blank pages are also held until a curator confirms they carry no content.
        raise OCRRequired(missing_text_pages)
    if not pages:
        raise SourceParseError("EMPTY_TEXT", "PDF contains no pages")
    return ParsedDocument(file_format, pages, None, [])

