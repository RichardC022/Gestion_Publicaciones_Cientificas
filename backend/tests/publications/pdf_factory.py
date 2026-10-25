"""Builders of PDF fixtures for the publications tests.

Every builder returns the bytes of a real PDF written by ``pikepdf``,
so the validation and sanitization tests run against genuine files and
not against hand-made strings.
"""

from __future__ import annotations

import io

import pikepdf
from pikepdf import Array, Dictionary, Name, String

MIB = 1024 * 1024


def _save(pdf: pikepdf.Pdf, **options) -> bytes:
    buffer = io.BytesIO()
    pdf.save(buffer, **options)
    return buffer.getvalue()


def clean_pdf(pages: int = 1) -> bytes:
    """A valid PDF without metadata, annotations or active content."""
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page()
    return _save(pdf)


def pdf_without_pages() -> bytes:
    return _save(pikepdf.new())


def pdf_with_identity() -> bytes:
    """A PDF whose metadata, XMP, annotations and form carry an identity."""
    pdf = pikepdf.new()
    pdf.add_blank_page()
    page = pdf.pages[0]
    pdf.docinfo["/Author"] = String("Ana López")
    pdf.docinfo["/Creator"] = String("Word de Ana")
    with pdf.open_metadata() as meta:
        meta["dc:creator"] = ["Ana López"]
    pdf.Root.PieceInfo = Dictionary(App=Dictionary(Private=String("ana")))
    page.PieceInfo = Dictionary(App=Dictionary(Private=String("ana")))
    page.Annots = Array(
        [
            pdf.make_indirect(
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Text,
                    Rect=Array([0, 0, 10, 10]),
                    Contents=String("Comentario de Ana"),
                )
            )
        ]
    )
    pdf.Root.AcroForm = Dictionary(Fields=Array([]))
    return _save(pdf)


def pdf_with_active_content(kind: str) -> bytes:
    """A PDF carrying exactly one kind of forbidden active content."""
    pdf = pikepdf.new()
    pdf.add_blank_page()
    page = pdf.pages[0]
    javascript = Dictionary(S=Name.JavaScript, JS=String("app.alert('x')"))
    launch = Dictionary(S=Name.Launch, F=String("calc.exe"))
    if kind == "/JavaScript":
        pdf.Root.Names = Dictionary(
            JavaScript=Dictionary(Names=Array([String("init"), pdf.make_indirect(javascript)]))
        )
    elif kind == "/OpenAction":
        pdf.Root.OpenAction = Dictionary(S=Name.GoTo, D=Array([page.obj, Name.Fit]))
    elif kind == "/AA":
        page.AA = Dictionary(O=pdf.make_indirect(Dictionary(S=Name.GoTo)))
    elif kind == "/Launch":
        page.Annots = Array(
            [
                pdf.make_indirect(
                    Dictionary(
                        Type=Name.Annot,
                        Subtype=Name.Link,
                        Rect=Array([0, 0, 10, 10]),
                        A=launch,
                    )
                )
            ]
        )
    elif kind == "/EmbeddedFiles":
        pdf.Root.Names = Dictionary(EmbeddedFiles=Dictionary(Names=Array([])))
    elif kind == "inline-javascript":
        # Acción escrita en línea dentro de /OpenAction (no es objeto indirecto).
        pdf.Root.OpenAction = javascript
    else:  # pragma: no cover - guard for typos in the tests
        raise ValueError(kind)
    return _save(pdf)


def encrypted_pdf(user_password: str) -> bytes:
    pdf = pikepdf.new()
    pdf.add_blank_page()
    return _save(pdf, encryption=pikepdf.Encryption(user=user_password, owner="owner"))


def pdf_of_size(target: int) -> bytes:
    """A valid PDF of exactly ``target`` bytes.

    A filler stream is resized until the saved file reaches the target;
    the length digits of the stream make the first attempts miss by a
    few bytes, so it converges in a couple of passes.
    """
    pdf = pikepdf.new()
    pdf.add_blank_page()
    filler = pdf.make_stream(b"")
    pdf.Root.Filler = filler
    options = {
        "compress_streams": False,
        "stream_decode_level": pikepdf.StreamDecodeLevel.none,
        "deterministic_id": True,
    }
    length = target - 2000
    for _ in range(6):
        filler.write(b"x" * length)
        data = _save(pdf, **options)
        if len(data) == target:
            return data
        length += target - len(data)
    raise AssertionError("no se alcanzó el tamaño exacto")  # pragma: no cover
