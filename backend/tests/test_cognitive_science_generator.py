import pytest
from app.adapters.ai.gemini_card_generator_adapter import (
    GeminiCardGeneratorAdapter,
    GeneratedCardSchema,
    GeneratedDeckSchema,
)
from app.domain.models import CardType, GenerationOptions
from app.core.formatting import format_anki_field, extract_breadcrumb_and_body


@pytest.fixture
def adapter():
    return GeminiCardGeneratorAdapter(
        api_key="mock_key",
        model="gemini-3.8-flash",
    )


def test_system_instruction_contains_all_cognitive_laws(adapter):
    options = GenerationOptions(
        deck_name="Medicina::Cardiología",
        card_type=CardType.BASIC,
        target_count=0,
        language="es",
    )
    instruction = adapter._build_system_instruction(options)

    # Law 1: Minimum information principle
    assert "Principio de Información Mínima" in instruction
    assert "5 A 8 SEGUNDOS" in instruction

    # Law 2: Hierarchical breadcrumbs
    assert "Anclaje Jerárquico Obligatorio" in instruction
    assert "[Macro-tema > Sub-tema > Categoría]" in instruction

    # Law 3: Elaborative Interrogation & Causal Mechanism
    assert "Interrogación Elaborativa y Mecanismo Causal" in instruction
    assert "Dunlosky" in instruction

    # Law 4: Reverse / Causal Cloze
    assert "Oclusión Causal Inversa" in instruction
    assert "Reverse / Causal Cloze" in instruction

    # Law 5: Discrimination Matrix / Interleaving
    assert "Matrices de Discriminación" in instruction
    assert "Interleaving" in instruction

    # Law 6: Hypercorrection Effect
    assert "Efecto de Hipercorrección" in instruction
    assert "Janet Metcalfe" in instruction
    assert "⚠️ Trampa frecuente / Error común:" in instruction

    # All 5 Archetypes present
    assert "Arquetipo A: Cloze Contextualizado Causal" in instruction
    assert "Arquetipo B: Matriz de Contraste" in instruction
    assert "Arquetipo C: Pregunta Atómica Elaborativa" in instruction
    assert "Arquetipo D: Tarjeta Radar" in instruction
    assert "Arquetipo E: Mini-Escenario Aplicado" in instruction


def test_schema_archetype_e_and_hypercorrection(adapter):
    sample_card = GeneratedCardSchema(
        archetype="Arquetipo E: Mini-Escenario Aplicado",
        front="[Medicina > Cardiología > Farmacología] Paciente asmático presenta taquicardia supraventricular. ¿Por qué está contraindicado el propranolol?",
        back="Porque bloquea receptores $\\beta_2$ bronquiales, desencadenando broncoespasmo grave.",
        tags=["medicina", "cardiologia"],
        explanation="**Mecanismo:** Propranolol es no selectivo (bloquea $\\beta_1$ y $\\beta_2$).\n\n⚠️ Trampa frecuente / Error común: Creer que todos los beta-bloqueantes tienen el mismo perfil de seguridad pulmonar; los $\\beta_1$ cardio-selectivos (como metoprolol) tienen menor riesgo relativo.",
    )
    assert sample_card.archetype.startswith("Arquetipo E")
    assert "⚠️ Trampa frecuente" in sample_card.explanation
    assert "$" in sample_card.back

    deck_schema = GeneratedDeckSchema(cards=[sample_card])
    domain_cards = adapter._map_to_domain(deck_schema, GenerationOptions(deck_name="Medicina"))

    assert len(domain_cards) == 1
    card = domain_cards[0]
    assert card.archetype == "Arquetipo E: Mini-Escenario Aplicado"
    assert card.card_type == CardType.BASIC

    # Format test with Anki core formatter
    breadcrumb, body = extract_breadcrumb_and_body(card.front)
    assert breadcrumb == "Medicina > Cardiología > Farmacología"
    assert "Paciente asmático" in body

    html_back = format_anki_field(card.back)
    assert "\\(" in html_back  # MathJax converted

    html_extra = format_anki_field(card.explanation)
    assert "⚠️ Trampa frecuente" in html_extra


def test_causal_cloze_mapping(adapter):
    sample_cloze = GeneratedCardSchema(
        archetype="Arquetipo A: Cloze Contextualizado Causal",
        front="[Redes > TCP > Control de Flujo] Al detectar congestión mediante triple ACK duplicado, el algoritmo Tahoe {{c1::reduce la ventana a 1 MSS}} en lugar de mantener la mitad.",
        back="",
        tags=["redes"],
        explanation="Tahoe resetea a 1 MSS (Slow Start brusco), a diferencia de Reno que aplica Fast Recovery.\n\n⚠️ Trampa frecuente / Error común: Confundir TCP Tahoe con Reno; Reno no baja a 1 MSS ante triple ACK.",
    )

    deck_schema = GeneratedDeckSchema(cards=[sample_cloze])
    domain_cards = adapter._map_to_domain(deck_schema, GenerationOptions(deck_name="Redes"))

    assert len(domain_cards) == 1
    card = domain_cards[0]
    assert card.card_type == CardType.CLOZE
    assert "{{c1::" in card.front
    assert "⚠️ Trampa frecuente" in card.explanation
