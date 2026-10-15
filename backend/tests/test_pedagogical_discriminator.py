import pytest
from app.domain.models import (
    CardType,
    FacetDiscriminationVerdict,
    FacetType,
    Flashcard,
)
from app.services.pedagogical_discriminator_service import (
    PedagogicalDiscriminatorService,
)


@pytest.fixture
def discriminator():
    return PedagogicalDiscriminatorService()


def test_discriminator_detects_real_collision_between_card2_and_card10(discriminator):
    """
    Gold Standard Collision Test:
    Card 2 and Card 10 both test the exact same atomic fact (ReAct interleaving reasoning and action).
    The discriminator MUST flag this as REDUNDANT_COLLISION.
    """
    card_2 = Flashcard(
        card_type=CardType.CLOZE,
        front="[IA Generativa > Agentes > Patrón ReAct] El patrón ReAct permite a un LLM resolver tareas complejas mediante {{c1::la intercalación de razonamiento y acciones con observaciones}}.",
        back="La intercalación de razonamiento y acciones con observaciones.",
    )

    card_10 = Flashcard(
        card_type=CardType.CLOZE,
        front="[ReAct > Beneficios > Arquitectura] El bucle fundamental de ReAct se compone de intercalar pasos de {{c1::razonamiento}} y acciones.",
        back="razonamiento",
    )

    result = discriminator.discriminate_pair(
        candidate_card=card_10,
        existing_text=f"{card_2.front} {card_2.back}",
        existing_card_id=card_2.id,
    )

    assert result.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION
    assert result.colliding_card_id == card_2.id
    assert "Colisión de objetivo cognitivo" in result.reasoning


def test_discriminator_approves_faceted_complements_for_same_entity(discriminator):
    """
    Gold Standard Complementarity Test:
    Card 1 (Components) and Card 5 (Stop Condition) both target 'ReAct',
    but exercise completely different cognitive facets.
    The discriminator MUST approve them as FACETED_COMPLEMENT.
    """
    card_1 = Flashcard(
        card_type=CardType.BASIC,
        front="[IA Generativa > Agentes > Patrón ReAct] ¿Qué dos componentes intercala de forma iterativa el patrón ReAct en su ejecución?",
        back="Pensamiento (Reasoning/Thought) y Acción (Action) orientada a herramientas externas.",
    )

    card_5 = Flashcard(
        card_type=CardType.BASIC,
        front="[IA Generativa > Agentes > Ciclo ReAct] ¿Cuál es la condición de salida que finaliza el bucle de trazabilidad (Trace Execution) en ReAct?",
        back="Cuando el modelo genera el estado 'Final Answer' tras resolver la tarea.",
    )

    result = discriminator.discriminate_pair(
        candidate_card=card_5,
        existing_text=f"{card_1.front} {card_1.back}",
        existing_card_id=card_1.id,
    )

    assert result.verdict == FacetDiscriminationVerdict.FACETED_COMPLEMENT
    assert result.candidate_facet == "Condición de Salida / Terminación"
    assert "Faceta complementaria válida" in result.reasoning


def test_discriminator_approves_data_source_vs_contrast(discriminator):
    """
    Verify Card 3 (Data source origin of Observation) vs Card 7 (Interpretability benefit).
    Both are about ReAct, but target distinct facets.
    """
    card_3 = Flashcard(
        card_type=CardType.BASIC,
        front="[IA Generativa > Agentes > Patrón ReAct] En el patrón ReAct, ¿de dónde proviene la información contenida en la 'Observación' (Observation)?",
        back="Del entorno externo o del resultado devuelto por la herramienta ejecutada.",
    )

    card_7 = Flashcard(
        card_type=CardType.BASIC,
        front="[ReAct > Beneficios > Transparencia] ¿Por qué el patrón ReAct mejora la interpretabilidad frente a métodos CoT tradicionales?",
        back="Porque entrelaza razonamiento verbal con trazas de acciones ejecutables.",
    )

    result = discriminator.discriminate_pair(
        candidate_card=card_7,
        existing_text=f"{card_3.front} {card_3.back}",
        existing_card_id=card_3.id,
    )

    assert result.verdict == FacetDiscriminationVerdict.FACETED_COMPLEMENT


@pytest.mark.asyncio
async def test_discriminator_audit_batch_filters_duplicates(discriminator):
    """
    Verify Level 1 batch audit: Card 2 passes, but Card 10 is caught as intra-batch collision.
    """
    cards = [
        Flashcard(
            id="card-1",
            card_type=CardType.BASIC,
            front="[Patrón ReAct] ¿Qué dos componentes intercala el bucle de ReAct?",
            back="Pensamiento y Acción.",
        ),
        Flashcard(
            id="card-2",
            card_type=CardType.CLOZE,
            front="[Patrón ReAct] ReAct resuelve tareas mediante {{c1::la intercalación de razonamiento y acciones}}.",
            back="la intercalación de razonamiento y acciones",
        ),
        Flashcard(
            id="card-5",
            card_type=CardType.BASIC,
            front="[Patrón ReAct] ¿Cuál es la condición de salida del bucle en ReAct?",
            back="Estado Final Answer.",
        ),
        Flashcard(
            id="card-10",
            card_type=CardType.CLOZE,
            front="[Patrón ReAct] El bucle se compone de intercalar pasos de {{c1::razonamiento y acciones}}.",
            back="razonamiento y acciones",
        ),
    ]

    results = await discriminator.audit_batch(cards)
    assert len(results) == 4

    # Card 1: approved
    assert results[0].is_approved is True
    # Card 2: approved
    assert results[1].is_approved is True
    # Card 5: approved (different facet: stop condition)
    assert results[2].is_approved is True
    # Card 10: rejected due to intra-batch collision with Card 2
    assert results[3].is_approved is False
    assert results[3].intra_batch_collision is not None
    assert results[3].intra_batch_collision.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION


class MockStore:
    def __init__(self, notes):
        self._notes = notes

    def semantic_search(self, deck_name, query_embedding, top_k=3, min_similarity=0.75, exclude_note_ids=None):
        return self._notes


class MockEmbeddingAdapter:
    async def get_embedding(self, text):
        return [0.1] * 768


@pytest.mark.asyncio
async def test_discriminator_detects_global_deck_collision():
    """
    Verify Level 2: Candidate card matches an existing note in the deck on the same fact.
    Must be caught as global_deck_collision.
    """
    mock_existing_note = {
        "note_id": 999123,
        "front": "[Patrón ReAct] El bucle fundamental intercala razonamiento y acciones.",
        "back": "razonamiento y acciones",
        "similarity": 0.91,
    }
    mock_store = MockStore(notes=[mock_existing_note])
    mock_embed = MockEmbeddingAdapter()

    service = PedagogicalDiscriminatorService(store=mock_store, embedding_adapter=mock_embed)

    candidate = Flashcard(
        id="new-cand",
        card_type=CardType.CLOZE,
        front="[Patrón ReAct] ReAct resuelve tareas mediante {{c1::la intercalación de razonamiento y acciones}}.",
        back="razonamiento y acciones",
    )

    results = await service.audit_batch([candidate], deck_name="Oracle Cloud")
    assert len(results) == 1
    assert results[0].is_approved is False
    assert results[0].global_deck_collision is not None
    assert results[0].global_deck_collision.colliding_note_id == 999123
    assert results[0].global_deck_collision.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION


@pytest.mark.asyncio
async def test_discriminator_approves_global_deck_faceted_complement():
    """
    Verify Level 2: Existing deck note is about ReAct mechanism, but candidate card is
    about ReAct stop condition. Must be APPROVED as a complementary facet.
    """
    mock_existing_note = {
        "note_id": 999123,
        "front": "[Patrón ReAct] El bucle fundamental intercala razonamiento y acciones.",
        "back": "razonamiento y acciones",
        "similarity": 0.82,
    }
    mock_store = MockStore(notes=[mock_existing_note])
    mock_embed = MockEmbeddingAdapter()

    service = PedagogicalDiscriminatorService(store=mock_store, embedding_adapter=mock_embed)

    candidate_stop_condition = Flashcard(
        id="new-stop",
        card_type=CardType.BASIC,
        front="[Patrón ReAct] ¿Cuál es la condición de salida que finaliza el bucle en ReAct?",
        back="El estado Final Answer.",
    )

    results = await service.audit_batch([candidate_stop_condition], deck_name="Oracle Cloud")
    assert len(results) == 1
    assert results[0].is_approved is True
    assert results[0].global_deck_collision is None
    assert "Faceta 'Condición de Salida / Terminación' complementaria" in results[0].audit_feedback


@pytest.mark.asyncio
async def test_discriminator_prunes_question_contrast_collision(discriminator):
    """
    Verify that two cards with DIFFERENT taxonomy breadcrumbs but asking the SAME
    structural contrast between CoT and ToT are caught as redundant collisions.
    """
    card_cot_1 = Flashcard(
        id="tot-card-2",
        card_type=CardType.BASIC,
        front="[IA Generativa > Técnicas de Prompting > Tree-of-Thoughts] ¿Qué diferencia estructural existe entre Chain-of-Thought (CoT) y Tree-of-Thoughts (ToT) respecto a las rutas de razonamiento exploradas?",
        back="CoT sigue una trayectoria lineal única, mientras ToT ramifica, evalúa y permite retroceder (backtracking).",
    )
    card_cot_2 = Flashcard(
        id="tot-card-6",
        card_type=CardType.BASIC,
        front="[IA > Prompt Engineering > Arquitecturas de Razonamiento] ¿Qué diferencia estructuralmente a Chain-of-Thought (CoT) de Tree of Thoughts (ToT) al resolver un problema complejo?",
        back="CoT genera una secuencia lineal directa; ToT explora ramificaciones múltiples con evaluación y retroceso.",
    )
    card_case_study = Flashcard(
        id="tot-card-7",
        card_type=CardType.BASIC,
        front="[IA > Prompt Engineering > Casos de Uso] Un agente necesita resolver un juego combinatorio con múltiples movimientos posibles y marcha atrás (backtracking). ¿Por qué se debe seleccionar ToT frente a CoT?",
        back="Permite ponderar caminos alternativos y retroceder ante estados inviables (búsqueda en espacio de estados).",
    )

    results = await discriminator.audit_batch([card_cot_1, card_cot_2, card_case_study])
    assert len(results) == 3
    assert results[0].is_approved is True
    assert results[1].is_approved is False
    assert results[1].intra_batch_collision is not None
    assert results[1].intra_batch_collision.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION
    # Card 3 is an application case study, must be approved
    assert results[2].is_approved is True


def test_discriminator_detects_error_cascade_cross_note_collision(discriminator):
    """
    Gold Standard Real-World Failure Reproduction Test:
    Note 5 evaluated error cascade in CoT.
    The old Note 6 Card 2 also evaluated error cascade in CoT.
    The discriminator MUST catch this as REDUNDANT_COLLISION.
    """
    card_note5 = Flashcard(
        id="cot-pkg5-c5",
        card_type=CardType.BASIC,
        front="[IA Generativa > Prompt Engineering > Chain of Thought] ¿Qué riesgo crítico se introduce cuando un modelo comete un error lógico al inicio de una cadena de Chain of Thought (CoT)?",
        back="Propagación de errores en cascada que invalida la conclusión final.",
    )

    card_note6_old = Flashcard(
        id="cot-pkg6-c2-old",
        card_type=CardType.BASIC,
        front="[Limitations of Standalone CoT > Propagation > Error Handling] ¿Qué sucede con un error lógico introducido en el primer paso de un razonamiento CoT aislado?",
        back="Se propaga y magnifica en los pasos posteriores.",
    )

    result = discriminator.discriminate_pair(
        candidate_card=card_note6_old,
        existing_text=f"{card_note5.front} {card_note5.back}",
        existing_card_id=card_note5.id,
    )

    assert result.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION
    assert result.colliding_card_id == card_note5.id
    assert "Colisión de objetivo cognitivo" in result.reasoning


def test_discriminator_approves_refocused_architectural_recovery_card(discriminator):
    """
    Verify that when Card 2 is properly refocused from the symptom (cascade)
    to the architectural cause (lack of external feedback loop),
    it is APPROVED as a valid complementary facet.
    """
    card_note5 = Flashcard(
        id="cot-pkg5-c5",
        card_type=CardType.BASIC,
        front="[IA Generativa > Prompt Engineering > Chain of Thought] ¿Qué riesgo crítico se introduce cuando un modelo comete un error lógico al inicio de una cadena de Chain of Thought (CoT)?",
        back="Propagación de errores en cascada que invalida la conclusión final.",
    )

    card_note6_refocused = Flashcard(
        id="cot-pkg6-c2-refocused",
        card_type=CardType.BASIC,
        front="[Limitations of Standalone CoT > Correction > Recovery Mechanism] ¿Por qué un modelo con CoT aislado es incapaz de recuperarse de un error lógico temprano?",
        back="Porque carece de un bucle de verificación externo o feedback ambiental que contraste sus premisas intermedias.",
    )

    result = discriminator.discriminate_pair(
        candidate_card=card_note6_refocused,
        existing_text=f"{card_note5.front} {card_note5.back}",
        existing_card_id=card_note5.id,
    )

    assert result.verdict == FacetDiscriminationVerdict.FACETED_COMPLEMENT


