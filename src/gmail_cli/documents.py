import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

TEXT_EXTENSIONS = (
    ".txt",
    ".csv",
    ".tsv",
    ".md",
    ".markdown",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".yaml",
    ".yml",
    ".rst",
)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF file."""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n\n--- Page Break ---\n\n".join(pages_text)
    except (PdfReadError, ValueError, OSError) as error:
        return f"Error extracting PDF text: {error}"


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract plain text from a Word (.docx) file."""
    try:
        with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
            if "word/document.xml" not in zf.namelist():
                return "Error: Invalid DOCX file (missing word/document.xml)"
            xml_content = zf.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            body = tree.find(".//w:body", ns)
            if body is None:
                return ""

            def get_p_text(p: ET.Element) -> str:
                parts = []
                for node in p.iter():
                    if node.tag == f"{{{ns['w']}}}t" and node.text:
                        parts.append(node.text)
                    elif node.tag == f"{{{ns['w']}}}tab":
                        parts.append("\t")
                    elif node.tag == f"{{{ns['w']}}}br":
                        parts.append("\n")
                return "".join(parts)

            output: list[str] = []
            for elem in body:
                tag = elem.tag
                if tag == f"{{{ns['w']}}}p":
                    t = get_p_text(elem)
                    if t:
                        output.append(t)
                elif tag == f"{{{ns['w']}}}tbl":
                    for row in elem.iterfind(".//w:tr", ns):
                        cell_texts = []
                        for cell in row.iterfind(".//w:tc", ns):
                            cell_text = " ".join(
                                get_p_text(p) for p in cell.iterfind(".//w:p", ns)
                            ).strip()
                            cell_texts.append(cell_text)
                        row_str = " | ".join(cell_texts).strip()
                        if row_str:
                            output.append(row_str)
            return "\n".join(output).strip()
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, OSError) as error:
        return f"Error extracting DOCX text: {error}"


def extract_attachment_text(
    filename: str, mime_type: str, file_bytes: bytes
) -> str | None:
    """Extract text from supported attachment document types (.pdf, .docx, .txt, .csv, .md, etc.)."""
    lower_fn = filename.lower()
    lower_mime = mime_type.lower()

    if "pdf" in lower_mime or lower_fn.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if "wordprocessingml" in lower_mime or lower_fn.endswith(".docx"):
        return extract_text_from_docx(file_bytes)

    if (
        lower_mime.startswith("text/")
        or any(lower_fn.endswith(ext) for ext in TEXT_EXTENSIONS)
        or lower_mime in ("application/json", "application/xml", "application/csv")
    ):
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return file_bytes.decode("latin-1")
            except UnicodeDecodeError, LookupError, ValueError:
                return file_bytes.decode("utf-8", errors="replace")

    return None
