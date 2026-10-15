from app.core.formatting import (
    format_anki_field,
    extract_breadcrumb_and_body,
    ANKICRAFT_BASIC_MODEL_NAME,
    ANKICRAFT_CLOZE_MODEL_NAME,
    BASIC_CARD_FRONT,
    BASIC_CARD_BACK,
    CLOZE_CARD_FRONT,
    CLOZE_CARD_BACK,
)


def test_format_anki_field_table_and_math():
    sample = (
        "| Unidad | Abreviatura | Equivalencia |\n"
        "| :--- | :--- | :--- |\n"
        "| Kilobits | Kbps | {{c1::$10^3$}} bps |\n\n"
        "Valores: $10^6$ bps."
    )
    res = format_anki_field(sample)
    assert "<table>" in res
    assert "Unidad</th>" in res
    assert "Kilobits</td>" in res
    assert r"\(10^6\)" in res
    assert r"{{c1::\(10^3\)}}" in res


def test_extract_breadcrumb_and_body():
    raw_front = "[Sistemas Operativos > Procesos] ¿Qué es un deadlock?"
    breadcrumb, body = extract_breadcrumb_and_body(raw_front)
    assert breadcrumb == "Sistemas Operativos > Procesos"
    assert body == "¿Qué es un deadlock?"

    no_breadcrumb = "¿Qué es la memoria virtual?"
    bc2, body2 = extract_breadcrumb_and_body(no_breadcrumb)
    assert bc2 == ""
    assert body2 == "¿Qué es la memoria virtual?"


def test_templates_contain_necessary_fields():
    assert "{{Front}}" in BASIC_CARD_FRONT
    assert "{{Back}}" in BASIC_CARD_BACK
    assert "{{#Breadcrumb}}" in BASIC_CARD_FRONT
    assert "{{#Breadcrumb}}" in BASIC_CARD_BACK
    assert "{{#Extra}}" in BASIC_CARD_BACK

    assert "{{cloze:Text}}" in CLOZE_CARD_FRONT
    assert "{{cloze:Text}}" in CLOZE_CARD_BACK
    assert "{{#Extra}}" in CLOZE_CARD_BACK


