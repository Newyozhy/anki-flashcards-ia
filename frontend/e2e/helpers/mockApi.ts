import { Page } from '@playwright/test';

export async function setupStandardApiMocks(page: Page) {
  // 1. Anki Status
  await page.route('**/api/anki/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        is_connected: true,
        available_decks: ['Oracle Cloud', 'Arquitectura Hexagonal'],
        error_message: null,
      }),
    });
  });

  // 2. Ollama Status
  await page.route('**/api/ollama/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        is_available: true,
        models: ['qwen2.5:14b', 'llama3.2:3b'],
        active_model: 'qwen2.5:14b',
      }),
    });
  });

  // 3. Pre-flight Study Plan Inspection (Both /cards/inspect and /study-plan/inspect)
  const inspectionPayload = {
    topic_name: 'Arquitectura de Redes en Oracle Cloud',
    target_deck: 'Oracle Cloud',
    summary: 'Fundamentos de aislamiento de red, tablas de ruta y puertas de enlace en OCI.',
    source_text: 'Oracle Cloud Infrastructure Networking Guide',
    prerequisites: [
      {
        concept: 'Redes Virtuales de Nube (VCN)',
        reason: 'Concepto fundacional para alojar subredes e instancias.',
        enriched_summary: 'Una VCN es una red definida por software en la nube de Oracle.',
        mode: 'anchor',
        recommended_deep_cards: 1,
        selected: true,
      },
      {
        concept: 'Políticas de Seguridad y Listas de Control',
        reason: 'Requerido para comprender el filtrado de paquetes stateful.',
        enriched_summary: 'Seguridad perimetral a nivel de subred y de VNIC.',
        mode: 'deep_dive',
        recommended_deep_cards: 3,
        selected: true,
      },
    ],
    core_themes: [
      {
        id: 'theme-vcn-subnets',
        title: 'Subredes Públicas vs Privadas',
        description: 'Diferenciación basada en el destino predeterminado hacia Internet Gateway.',
        recommended_cards: 2,
        selected: true,
        match_info: { status: 'gap' },
      },
      {
        id: 'theme-route-tables',
        title: 'Tablas de Enrutamiento y Reglas de Salto',
        description: 'Direccionamiento de tráfico hacia NAT Gateway y Service Gateway.',
        recommended_cards: 2,
        selected: true,
        match_info: { status: 'complementary' },
      },
    ],
  };

  await page.route('**/api/cards/inspect*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(inspectionPayload),
    });
  });

  await page.route('**/api/study-plan/inspect*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(inspectionPayload),
    });
  });

  // 4. Streamed Flashcards Generation
  await page.route('**/api/cards/generate/text-stream', async (route) => {
    const sseBody = [
      'data: ' +
        JSON.stringify({
          event_type: 'batch',
          batch_label: 'VCN y Subredes OCI',
          current_batch: 1,
          total_batches: 1,
          accumulated_count: 2,
          cards: [
            {
              id: 'card-e2e-1',
              card_type: 'cloze',
              front:
                'Una subred pública en OCI se caracteriza por tener una ruta por defecto hacia un {{c1::Internet Gateway (IGW)}}.',
              back: 'Internet Gateway (IGW)',
              explanation: 'Permite bidireccionalidad con direcciones IP públicas asignadas.',
              tags: ['oracle-cloud', 'networking'],
            },
            {
              id: 'card-e2e-2',
              card_type: 'basic',
              front:
                '¿Cuál es la fórmula teórica del ancho de banda según Hartley-Shannon: $C = B \\log_2(1 + \\text{SNR})$?',
              back: 'Determina la capacidad máxima en bits por segundo en presencia de ruido gaussiano.',
              explanation: 'Límite físico fundamental en redes de telecomunicaciones.',
              tags: ['oracle-cloud', 'teoria'],
            },
          ],
        }),
      '',
      'data: ' +
        JSON.stringify({
          event_type: 'done',
          cards: [],
          audit_report: {
            average_quality_score: 95,
            total_cards_repaired: 1,
            total_sister_cards_created: 0,
            card_reports: [
              {
                card_id: 'card-e2e-1',
                score: 95,
                passed: true,
                findings: [],
              },
            ],
          },
        }),
      '',
    ].join('\n\n');

    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: {
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
      body: sseBody,
    });
  });

  // 5. Sanitation Queue
  await page.route('**/api/anki/decks/*/sanitation-queue', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        deck_name: 'Oracle Cloud',
        total_count: 2,
        pending_count: 2,
        sanitized_count: 0,
        notes: [
          {
            note_id: 201,
            front: 'Nota monolito con 15 conceptos mezclados de IAM y VCN en un solo párrafo',
            back: 'Respuesta excesiva que satura la memoria de trabajo',
            clean_front: 'Nota monolito IAM y VCN',
            raw_fields: { Front: 'Nota monolito IAM y VCN', Back: 'Respuesta excesiva' },
            tags: ['deuda', 'redes'],
            quality_status: 'bad',
            topological_rank: 0,
            subtopic_descriptor: 'Gobernanza y Redes',
            media_files: [],
          },
          {
            note_id: 202,
            front: 'Concepto complejo de Block Volume vs Object Storage sin atomizar',
            back: 'Respuesta monolítica',
            clean_front: 'Block Volume vs Object Storage',
            raw_fields: { Front: 'Block Volume vs Object Storage', Back: 'Respuesta monolítica' },
            tags: ['deuda', 'storage'],
            quality_status: 'bad',
            topological_rank: 1,
            subtopic_descriptor: 'Almacenamiento',
            media_files: [],
          },
        ],
      }),
    });
  });

  // 5b. Transactional Note Replace
  await page.route('**/api/anki/decks/*/replace-note', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        deleted_note_id: 201,
        created_cards_count: 2,
        remaining_in_queue: 1,
      }),
    });
  });

  // 6. Socratic Node Mastery Challenge
  await page.route('**/api/anki/decks/*/nodes/*/socratic-challenge', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        deck_name: 'Oracle Cloud',
        concept_id: 'redes_virtuales_de_nube_vcn',
        concept_name: 'Redes Virtuales de Nube (VCN)',
        challenge: {
          concept_id: 'redes_virtuales_de_nube_vcn',
          concept_name: 'Redes Virtuales de Nube (VCN)',
          challenge_question: '¿Por qué dos VCNs con bloques CIDR idénticos no pueden conectarse mediante un Local Peering Gateway?',
          scenario_context: 'Un arquitecto intenta conectar la VCN de Producción (10.0.0.0/16) con la VCN de Desarrollo (10.0.0.0/16).',
          evaluation_criteria: [
            'Explicar el solapamiento de bloques CIDR y ambigüedad de enrutamiento',
            'Identificar la imposibilidad de resolver el salto de paquete a nivel capa 3',
          ],
        },
        eligible_for_mastery: true,
      }),
    });
  });

  // 7. Socratic Node Mastery Evaluation
  await page.route('**/api/anki/decks/*/nodes/*/socratic-evaluate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        deck_name: 'Oracle Cloud',
        concept_id: 'redes_virtuales_de_nube_vcn',
        passed: true,
        score: 0.95,
        feedback: 'Excelente explicación. Demostraste comprensión profunda de la ambigüedad en tablas de ruta generada por CIDRs superpuestos.',
        new_node_status: 'optimal',
      }),
    });
  });

  // 8. Deck Studio: Index Status
  await page.route('**/api/anki/decks/*/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        deck_name: 'Oracle Cloud',
        total_notes: 14,
        indexed_nodes_count: 8,
        clusters_count: 3,
        is_stale: false,
        last_sync: '2026-10-13T20:00:00Z',
      }),
    });
  });

  // 9. Deck Studio: Cognitive DAG
  await page.route('**/api/anki/decks/*/dag', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        deck_name: 'Oracle Cloud',
        nodes: [
          {
            id: 'dag-node-1',
            concept_name: 'Tenancy & Compartments',
            cluster_name: 'Gobernanza',
            cluster_id: 'c-gov',
            topological_rank: 0,
            in_degree: 0,
            out_degree: 2,
            note_ids: [101, 102],
          },
          {
            id: 'dag-node-2',
            concept_name: 'Virtual Cloud Network (VCN)',
            cluster_name: 'Networking',
            cluster_id: 'c-net',
            topological_rank: 1,
            in_degree: 1,
            out_degree: 1,
            note_ids: [103],
          },
          {
            id: 'dag-node-3',
            concept_name: 'Security Lists & NSGs',
            cluster_name: 'Networking',
            cluster_id: 'c-net',
            topological_rank: 2,
            in_degree: 2,
            out_degree: 0,
            note_ids: [104],
          },
        ],
        edges: [
          {
            source: 'dag-node-1',
            target: 'dag-node-2',
            relationship: 'prerequisite',
          },
          {
            source: 'dag-node-2',
            target: 'dag-node-3',
            relationship: 'prerequisite',
          },
        ],
      }),
    });
  });

  // 10. Deck Studio: Debt Report
  await page.route('**/api/anki/decks/*/debt-report', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total_debt_notes: 2,
        debt_ratio: 0.14,
        bad_notes: [
          {
            note_id: 201,
            front: 'Nota monolito IAM y VCN',
            back: 'Texto excesivo',
            heuristic_failures: ['Exceso de tokens', 'Falta de atomicidad'],
          },
        ],
      }),
    });
  });

  // 11. Deck Studio: Duplicates Report
  await page.route('**/api/anki/decks/*/duplicates*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        duplicate_clusters: [],
        total_potential_duplicates: 0,
        pairs: [],
      }),
    });
  });

  // 12. Deck Studio: Orphans / Gaps
  await page.route('**/api/anki/decks/*/orphans', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        orphan_gaps: [
          {
            gap_title: 'Dynamic Routing Gateway (DRG)',
            reason: 'Concepto desconectado del grafo principal sin dependencias ancladas',
            suggested_front: '¿Cuál es la función del DRG en conexiones Site-to-Site VPN?',
          },
        ],
      }),
    });
  });

  // 13. Deck Studio: Coverage Map
  await page.route('**/api/anki/decks/*/coverage-map*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        deck_name: 'Oracle Cloud',
        total_nodes: 3,
        covered_nodes: 2,
        coverage_ratio: 0.67,
        nodes: [
          { id: 'cm-1', label: 'Tenancy', status: 'optimal' },
          { id: 'cm-2', label: 'Networking', status: 'debt' },
        ],
        edges: [],
      }),
    });
  });

  // 14. Deck Studio: Audits History
  await page.route('**/api/anki/decks/*/audits*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        audits: [],
        total_count: 0,
      }),
    });
  });

  // 15. Deck Studio: Semantic Clusters
  await page.route('**/api/anki/decks/*/clusters', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        clusters: [
          {
            cluster_id: 'c-net',
            cluster_name: 'Networking & Gateways',
            notes_count: 4,
            health_score: 85,
          },
        ],
      }),
    });
  });

  // 16. Deck Studio: Learning Contract
  await page.route('**/api/anki/decks/*/interview/contract*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        deck_name: 'Oracle Cloud',
        target_audience: 'Ingenieros Cloud',
        goals: ['Certificación OCI Architect Associate'],
        rules: ['Atomicidad estricta', 'Evitar clozes ambiguos'],
      }),
    });
  });

  // 17. Deck Studio: Expansion Queue
  await page.route('**/api/anki/decks/*/expansion-queue*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [],
        total_count: 0,
      }),
    });
  });

  // 18. Export to APKG
  await page.route('**/api/cards/export/apkg', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/octet-stream',
      headers: {
        'Content-Disposition': 'attachment; filename="Oracle_Cloud.apkg"',
      },
      body: Buffer.from('FAKE_APKG_BINARY_PAYLOAD'),
    });
  });

  // 19. Export to AnkiConnect
  await page.route('**/api/cards/export/anki', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        cards_exported_count: 2,
        deleted_notes_count: 0,
        message: '¡2 tarjetas atómicas inyectadas con éxito en Anki Desktop!',
      }),
    });
  });
}
