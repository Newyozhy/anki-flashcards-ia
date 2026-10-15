import pytest
from app.domain.models import (
    GenerationOptions,
    CardType,
    StudyPlanInspection,
    CoreTheme,
    PrerequisiteItem,
    Flashcard,
)
from app.adapters.ai.gemini_card_generator_adapter import (
    GeminiCardGeneratorAdapter,
    GeneratedCardSchema,
    GeneratedDeckSchema,
    InspectedStudyPlanSchema,
    InspectedCoreThemeSchema,
    InspectedPrerequisiteSchema,
)

# Realistic Dense Technical Corpus: Distributed Consensus (Raft vs Paxos, RSM, Network Partitions)
DENSE_CORPUS_RAFT = """
El problema del consenso en sistemas distribuidos asíncronos bajo el modelo de fallas Crash-Recovery (CFT)
exige que un conjunto de nodos distribuidos acuerden una secuencia idéntica de comandos a ejecutar en sus
respectivas Máquinas de Estados Replicadas (RSM). A diferencia de Paxos, que desacopla el acuerdo por instancias
mediante dos fases (Prepare/Promise y Accept/Accepted) con roles móviles de Proposers, Acceptors y Learners,
el algoritmo Raft descompone deliberadamente el consenso en tres subproblemas ortogonales: Elección de Líder,
Replicación de Logs y Seguridad (Safety Invariants).

En Raft, el tiempo se divide en Términos lógicos arbitrarios identificados por enteros monótonamente crecientes.
Cada término actúa como un reloj lógico de Lamport y comienza con una elección. Un nodo puede residir en uno de
tres estados: Follower, Candidate o Leader. Si un Follower experimenta un timeout de heartbeat (aleatorizado
entre 150ms y 300ms para mitigar el Split-Vote), transiciona a Candidate, incrementa el término actual, vota por
sí mismo y emite RPCs RequestVote en paralelo a todos los demás pares del clúster.

Para ser electo, el candidato debe acumular votos de una mayoría estricta (quórum) de nodos: Q = floor(N/2) + 1.
Sin embargo, no cualquier nodo con votos mayoritarios puede ser líder: la regla de Elección Restringida
(Election Restriction) impone que un Follower sólo votará afirmativamente si el log del candidato está al menos
tan actualizado como el suyo propio. La comparación lexicográfica de actualización de log determina que: (1) un
log con mayor término en su última entrada es más actualizado; (2) a igual término final, el log con mayor longitud
(mayor log index) es el más actualizado. Esta invariante garantiza de forma matemática la propiedad 'Leader Completeness':
si una entrada de log fue comprometida (committed) en un término dado, estará presente sin excepción en los logs
de todos los líderes electos en términos superiores.

Una vez electo, el líder maneja todas las operaciones cliente. Cada comando se añade como una entrada de log no
comprometida con el término actual. El líder envía RPCs AppendEntries a los Followers. Una entrada se considera
'Committed' una vez que ha sido replicada exitosamente en una mayoría estricta de nodos y el líder ha replicado al
menos una entrada de su propio término actual. No obstante, Raft prohíbe explícitamente que un líder comprometa
entradas de términos anteriores contando réplicas directas; sólo puede comprometerlas de manera indirecta
comprometiendo una entrada de su término corriente. Este detalle sutil evita la anomalía clásica descrita en la
Figura 8 del paper original de Ongaro y Ousterhout, donde una entrada antigua replicada en la mayoría podría ser
sobrescrita por un líder posterior si se permitiera el commit directo de términos pasados.

En escenarios de partición de red asimétrica (Split-Brain), un líder aislado en la partición minoritaria (ej. 2 de 5 nodos)
puede continuar recibiendo escrituras de clientes, pero nunca alcanzará el quórum de AppendEntries (Q=3), por lo que
esas entradas quedarán permanentemente sin comprometer (uncommitted). Mientras tanto, en la partición mayoritaria
(3 de 5 nodos), los Followers detectarán la ausencia de heartbeats, elevarán el término y elegirán un nuevo líder válido
capaz de comprometer transacciones. Al resolverse la partición, el líder viejo recibirá un AppendEntries con un término
superior, detectará su obsolescencia y degradará inmediatamente su estado a Follower, truncando sus logs no comprometidos
para sincronizarse con el log canónico del nuevo líder.
"""


def test_dense_system_instruction_construction_and_budget():
    """Verify that dense multi-faceted prompts with prerequisites and themes are properly budgeted."""
    adapter = GeminiCardGeneratorAdapter(
        api_key="mock_key",
        model="gemini-3.8-flash",
        tier_models=["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"],
    )

    prereqs = (
        "- RPC (Remote Procedure Call): Protocolo de invocación remota sincrónica.\n"
        "- Máquinas de Estados Replicadas (RSM): Paradigma formal para tolerancia a fallas.\n"
        "- Partición de Red (Split-Brain): Falla donde nodos quedan incomunicados en subconjuntos.\n"
        "- Quórum de Mayoría Matemática: Regla de consenso donde Q = floor(N/2) + 1.\n"
        "- Write-Ahead Logging (WAL): Técnica de persistencia donde el log se escribe antes del estado."
    )

    themes = [
        "Elección de Líder y Temporizadores Aleatorios",
        "Regla de Elección Restringida (Log Up-to-Date Comparison)",
        "Invariante Leader Completeness y Prevención de Anomalía Figura 8",
        "AppendEntries Heartbeats y Replicación de Log",
        "Resolución de Partición de Red y Truncamiento de Logs Divergentes",
    ]

    options = GenerationOptions(
        deck_name="Sistemas Distribuidos::Raft",
        card_type=CardType.BASIC,
        target_count=15,
        prerequisites_context=prereqs,
        selected_themes=themes,
    )

    instruction = adapter._build_system_instruction(options)

    # 1. Verification of cognitive laws presence
    assert "Principio de Información Mínima" in instruction
    assert "Anclaje Jerárquico Obligatorio" in instruction
    assert "Interrogación Elaborativa" in instruction
    assert "Matrices de Discriminación" in instruction
    assert "Efecto de Hipercorrección" in instruction

    # 2. Verification of strict scaffolding directives
    assert "PRERREQUISITOS Y CONCEPTOS BASE ANCLADOS (MANDATORIO)" in instruction
    assert "RPC (Remote Procedure Call)" in instruction
    assert "Quórum de Mayoría Matemática" in instruction
    assert "[Fundamentos > Nombre]" in instruction
    assert "prerrequisito" in instruction

    # 3. Verification of core themes directives
    assert "EJES TEMÁTICOS PRIORIZADOS" in instruction
    for theme in themes:
        assert theme in instruction

    # 4. Prompt size inspection: system instruction should be concise yet complete
    char_length = len(instruction)
    # Roughly ~4000-5000 characters is ideal: detailed instructions without token bloat
    assert 3000 < char_length < 8000, f"System instruction length {char_length} is out of optimal bounds"


def test_dense_material_inspection_scaffolding_mapping():
    """Verify that a complex 6-theme and 5-prerequisite inspection maps perfectly to domain entities."""
    adapter = GeminiCardGeneratorAdapter(api_key="mock_key", model="gemini-3.8-flash")

    schema = InspectedStudyPlanSchema(
        topic_name="Consenso Distribuido Raft",
        self_sufficiency_score=65,
        self_sufficiency_verdict="El texto explica detalladamente la mecánica de Raft, pero asume que el estudiante comprende qué es un quórum mayoritario y cómo funciona una máquina de estados replicada sin definir sus propiedades formales.",
        suggested_total_cards=15,
        core_themes=[
            InspectedCoreThemeSchema(
                title="Elección de Líder & Split-Vote",
                description="Mecanismo de timers aleatorios y transición Follower -> Candidate",
                recommended_cards=3,
            ),
            InspectedCoreThemeSchema(
                title="Elección Restringida",
                description="Comparación de última entrada de log para otorgar votos",
                recommended_cards=2,
            ),
            InspectedCoreThemeSchema(
                title="Leader Completeness & Figura 8",
                description="Invariante de commit indirecto para términos pasados",
                recommended_cards=4,
            ),
            InspectedCoreThemeSchema(
                title="AppendEntries & Replicación",
                description="Propagación de entradas y compromiso por quórum",
                recommended_cards=3,
            ),
            InspectedCoreThemeSchema(
                title="Recuperación tras Split-Brain",
                description="Degradación de líder obsoleto y truncamiento de log",
                recommended_cards=3,
            ),
        ],
        prerequisites=[
            InspectedPrerequisiteSchema(
                concept="Quórum de Mayoría",
                reason="Esencial para entender por qué dos líderes no pueden elegirse en el mismo término",
                is_covered_in_text=False,
                search_query="quorum mayoria sistemas distribuidos consenso interseccion",
            ),
            InspectedPrerequisiteSchema(
                concept="Máquina de Estados Replicada (RSM)",
                reason="Es el objetivo final de Raft: mantener estados idénticos ante fallas",
                is_covered_in_text=True,
                search_query="replicated state machine distributed systems concepto",
            ),
            InspectedPrerequisiteSchema(
                concept="Relojes Lógicos de Lamport",
                reason="Raft utiliza términos lógicos monótonos para detectar obsolescencia temporal",
                is_covered_in_text=False,
                search_query="lamport logical clock term numbers consenso",
            ),
        ],
    )

    domain_plan = adapter._map_inspection_to_domain(schema)

    assert domain_plan.topic_name == "Consenso Distribuido Raft"
    assert domain_plan.self_sufficiency_score == 65
    assert len(domain_plan.core_themes) == 5
    assert len(domain_plan.prerequisites) == 3

    # Check total recommended cards calculation
    total_recommended = sum(t.recommended_cards for t in domain_plan.core_themes)
    assert total_recommended == 15

    # Check that missing prerequisites are marked correctly
    uncovered = [p for p in domain_plan.prerequisites if not p.is_covered_in_text]
    assert len(uncovered) == 2
    assert uncovered[0].concept == "Quórum de Mayoría"
    assert uncovered[1].concept == "Relojes Lógicos de Lamport"


def test_dense_batch_card_validation_and_atomicity():
    """Verify that a batch of cards for dense material strictly respects cognitive laws and atomicity."""
    adapter = GeminiCardGeneratorAdapter(api_key="mock_key", model="gemini-3.8-flash")

    # Generate a realistic batch of cards covering prerequisites and core themes
    mock_deck = GeneratedDeckSchema(
        cards=[
            # Prerequisite Card 1
            GeneratedCardSchema(
                archetype="Arquetipo C: Pregunta Atómica",
                front="[Fundamentos > Quórum de Mayoría] ¿Por qué es matemáticamente imposible que existan dos quórums independientes en un clúster de $N$ nodos?",
                back="Porque dos conjuntos de tamaño $\\lfloor N/2 \\rfloor + 1$ siempre intersectan en al menos un nodo.",
                tags=["distribuidos", "prerrequisito", "fundamentos"],
                explanation="Diagrama de Venn:\n[Quórum A (3)] ∩ [Quórum B (3)] = Nodo Compartido\n\n⚠️ Trampa frecuente / Error común: Creer que quórum significa el 100% de los nodos; basta una mayoría estricta.",
            ),
            # Prerequisite Card 2
            GeneratedCardSchema(
                archetype="Arquetipo C: Pregunta Atómica",
                front="[Fundamentos > Relojes Lógicos] ¿Qué función cumple el número de término (Term) en Raft?",
                back="Actúa como un reloj lógico monótono para detectar y descartar inmediatamente líderes o mensajes obsoletos.",
                tags=["distribuidos", "prerrequisito"],
                explanation="Term 1 < Term 2 -> Todo mensaje con Term 1 se invalida.\n\n⚠️ Trampa frecuente / Error común: Confundir término lógico con tiempo de reloj físico (NTP).",
            ),
            # Core Theme Card: Cloze Causal
            GeneratedCardSchema(
                archetype="Arquetipo A: Cloze Contextualizado",
                front="[Raft > Elección > Split-Vote] Para mitigar el riesgo de votos divididos (Split-Vote) donde ningún candidato alcanza la mayoría, Raft establece que el timeout de elección de cada nodo debe ser {{c1::aleatorizado}} en un rango entre 150ms y 300ms.",
                back="aleatorizado (evita que múltiples nodos se conviertan en candidatos al unísono)",
                tags=["sistemas-distribuidos", "raft", "eleccion"],
                explanation="Timers desfasados:\nNodo A: 160ms -> Inicia elección primero\nNodo B: 240ms -> Vota por A antes de su propio timeout\n\n⚠️ Trampa frecuente / Error común: Pensar que un timeout fijo idéntico en todos los nodos es más determinista; provoca split-votes infinitos.",
            ),
            # Core Theme Card: Matriz de Contraste
            GeneratedCardSchema(
                archetype="Arquetipo B: Matriz de Contraste",
                front="[Raft > Elección Restringida > Comparación de Logs]\n| Criterio de Actualización | Comparación Primaria | Comparación Secundaria (a igualdad) |\n| :--- | :--- | :--- |\n| Log más actualizado | {{c1::Mayor término en última entrada}} | {{c2::Mayor longitud de log (log index)}} |",
                back="c1: Mayor término en última entrada; c2: Mayor longitud de log",
                tags=["raft", "safety", "eleccion"],
                explanation="Regla: (lastTerm_A > lastTerm_B) OR (lastTerm_A == lastTerm_B AND lastIndex_A >= lastIndex_B)\n\n⚠️ Trampa frecuente / Error común: Creer que un log más largo siempre gana; si tiene un término menor, está obsoleto.",
            ),
            # Core Theme Card: Mini-Escenario Aplicado
            GeneratedCardSchema(
                archetype="Arquetipo E: Mini-Escenario Aplicado",
                front="[Raft > Split-Brain > Partición Minoritaria] Clúster de 5 nodos sufre partición: Líder L1 queda aislado con N2 (2 nodos), mientras N3, N4, N5 (3 nodos) forman la otra partición. Un cliente envía un comando de escritura a L1. ¿Qué ocurrirá con esa entrada?",
                back="L1 la escribirá en su log local pero NUNCA la comprometerá (uncommitted) por falta de quórum ($2 < 3$).",
                tags=["raft", "split-brain", "escenario"],
                explanation="Partición A: {L1, N2} -> Imposible quórum (2/5)\nPartición B: {N3, N4, N5} -> Elige L2 con quórum (3/5)\n\n⚠️ Trampa frecuente / Error común: Asumir que el líder aislado rechaza el socket de inmediato; el cliente se bloquea o recibe timeout.",
            ),
        ]
    )

    domain_cards = adapter._map_to_domain(
        mock_deck, GenerationOptions(deck_name="Raft", card_type=CardType.BASIC)
    )

    assert len(domain_cards) == 5

    for card in domain_cards:
        # Check cognitive rule: must have breadcrumbs in front
        assert card.front.startswith("["), f"Card front missing breadcrumbs: {card.front}"
        assert "]" in card.front, f"Card front missing closing breadcrumb bracket: {card.front}"

        # Check explanation has hypercorrection section
        assert card.explanation is not None, "Explanation field cannot be None"
        assert "⚠️ Trampa frecuente / Error común:" in card.explanation, (
            f"Missing hypercorrection warning in: {card.explanation}"
        )

        # Check atomic back length
        if card.card_type != CardType.CLOZE and card.back:
            word_count = len(card.back.split())
            assert word_count <= 25, f"Back is too wordy ({word_count} words): {card.back}"

    # Check that prerequisite cards exist and are marked properly
    prereq_cards = [c for c in domain_cards if "prerrequisito" in c.tags or "Fundamentos" in c.front]
    assert len(prereq_cards) == 2
    assert any("Quórum de Mayoría" in c.front for c in prereq_cards)
    assert any("Relojes Lógicos" in c.front for c in prereq_cards)


def test_partitioned_pipeline_theme_chunking_and_cards_estimation():
    """Verify that theme chunking and card estimation correctly partition study plans."""
    adapter = GeminiCardGeneratorAdapter(api_key="mock_key", model="gemini-3.8-flash")

    themes = [
        "Elección de Líder en Raft (~3 tarjetas)",
        "Replicación de Log (~4 tarjetas)",
        "Quórum y Particiones (~2 tarjetas)",
        "Compromiso Indirecto Figura 8 (~3 tarjetas)",
        "Log Compaction y Snapshots (~2 tarjetas)",
    ]

    chunks = adapter._chunk_themes(themes, max_per_chunk=2)
    assert len(chunks) == 3
    assert len(chunks[0]) == 2
    assert len(chunks[1]) == 2
    assert len(chunks[2]) == 1

    # Check card estimation
    cards_chunk_0 = adapter._estimate_chunk_cards(chunks[0])
    assert cards_chunk_0 == 7  # 3 + 4

    cards_chunk_1 = adapter._estimate_chunk_cards(chunks[1])
    assert cards_chunk_1 == 5  # 2 + 3

    cards_chunk_2 = adapter._estimate_chunk_cards(chunks[2])
    assert cards_chunk_2 == 2


@pytest.mark.asyncio
async def test_partitioned_pipeline_end_to_end_mock_execution():
    """Verify that the partitioned pipeline executes prerequisites and theme chunks, combining them cleanly."""
    from unittest.mock import MagicMock, patch

    adapter = GeminiCardGeneratorAdapter(api_key="mock_key", model="gemini-3.8-flash")
    adapter._get_client = MagicMock()

    options = GenerationOptions(
        deck_name="Sistemas Distribuidos::Raft",
        card_type=CardType.BASIC,
        prerequisites_context="- Quórum de Mayoría: Se requiere Q = floor(N/2)+1 para evitar split-brain.",
        selected_themes=[
            "Elección de Líder (~2 tarjetas)",
            "Replicación de Log (~2 tarjetas)",
        ],
    )

    prereq_deck = GeneratedDeckSchema(
        cards=[
            GeneratedCardSchema(
                archetype="Arquetipo C: Pregunta Atómica",
                front="[Fundamentos > Quórum de Mayoría] ¿Por qué no pueden coexistir dos quórums?",
                back="Porque dos mayorías estrictas siempre intersectan en al menos un nodo.",
                tags=["fundamentos", "prerrequisito"],
                explanation="⚠️ Trampa frecuente / Error común: Confundir quórum con unanimidad.",
            )
        ]
    )

    theme_deck = GeneratedDeckSchema(
        cards=[
            GeneratedCardSchema(
                archetype="Arquetipo A: Cloze Contextualizado",
                front="[Raft > Elección de Líder] El timeout de elección es {{c1::aleatorizado}}.",
                back="aleatorizado",
                tags=["eleccion", "raft"],
                explanation="⚠️ Trampa frecuente / Error común: Creer que los timeouts fijos evitan split-votes.",
            ),
            GeneratedCardSchema(
                archetype="Arquetipo C: Pregunta Atómica",
                front="[Raft > Replicación de Log] ¿Cuándo se compromete una entrada de log?",
                back="Al replicarse en la mayoría del clúster con una entrada del término corriente.",
                tags=["replicacion", "raft"],
                explanation="⚠️ Trampa frecuente / Error común: Replicar en minorías no garantiza durabilidad.",
            ),
        ]
    )

    async def mock_race(client, contents, instruction, response_schema=None):
        if "CIMIENTOS COGNITIVOS" in instruction:
            return prereq_deck
        return theme_deck

    with patch.object(adapter, "_race_hedged_generation", side_effect=mock_race):
        result_cards = await adapter._execute_generation(
            contents=["Contenido sobre Raft"], options=options
        )

        assert len(result_cards) == 3
        # First card must be the prerequisite foundation card
        assert "Fundamentos" in result_cards[0].front
        assert "prerrequisito" in result_cards[0].tags
        # Following cards are the core theme cards
        assert "Elección de Líder" in result_cards[1].front
        assert "Replicación de Log" in result_cards[2].front


@pytest.mark.asyncio
async def test_partitioned_pipeline_failure_isolation_preserves_successful_cards():
    """Verify that if one theme chunk fails, successful chunks and prerequisite cards are preserved."""
    from unittest.mock import MagicMock, patch

    adapter = GeminiCardGeneratorAdapter(api_key="mock_key", model="gemini-3.8-flash")
    adapter._get_client = MagicMock()

    options = GenerationOptions(
        deck_name="Raft",
        prerequisites_context="- Quórum: Mayoría estricta.",
        selected_themes=[
            "Tema A (~2 tarjetas)",
            "Tema B (~2 tarjetas)",
        ],
    )

    prereq_deck = GeneratedDeckSchema(
        cards=[
            GeneratedCardSchema(
                archetype="Arquetipo C",
                front="[Fundamentos > Quórum] ¿Qué es?",
                back="Mayoría estricta.",
                tags=["prerrequisito"],
                explanation="⚠️ Trampa frecuente / Error común: Quórum != 100%.",
            )
        ]
    )

    # Let's say chunk 0 fails while prerequisite succeeds
    async def mock_race(client, contents, instruction, response_schema=None):
        if "CIMIENTOS COGNITIVOS" in instruction:
            return prereq_deck
        raise RuntimeError("API timeout on this specific theme batch")

    with patch.object(adapter, "_race_hedged_generation", side_effect=mock_race):
        result_cards = await adapter._execute_generation(
            contents=["Contenido sobre Raft"], options=options
        )

        # Prerequisite card is NOT lost despite theme batch failure!
        assert len(result_cards) == 1
        assert "Fundamentos > Quórum" in result_cards[0].front

