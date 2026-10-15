import { test, expect } from '@playwright/test';
import { setupStandardApiMocks } from './helpers/mockApi';

test.describe('Flujo B: Cockpit de Saneamiento Quirúrgico y Sustitución Transaccional', () => {
  test.beforeEach(async ({ page }) => {
    await setupStandardApiMocks(page);

    // Seed session storage with selected card and generated atomic cards (pure live flow without orphan sanitation_mode)
    await page.addInitScript(() => {
      const activeNote = {
        note_id: 201,
        front: 'Nota monolito IAM y VCN',
        back: 'Respuesta excesiva',
        clean_front: 'Nota monolito IAM y VCN',
        raw_fields: { Front: 'Nota monolito IAM y VCN', Back: 'Respuesta excesiva' },
        tags: ['deuda'],
        quality_status: 'bad',
        topological_rank: 0,
        subtopic_descriptor: 'Gobernanza y Redes',
        media_files: [],
      };
      sessionStorage.setItem('ankicraft_selected_anki_card', JSON.stringify(activeNote));

      const generatedAtomicCards = [
        {
          id: 'card-atom-1',
          card_type: 'basic',
          front: '¿Qué es una VCN en Oracle Cloud?',
          back: 'Una red definida por software con aislamiento de tráfico.',
          tags: ['oracle-cloud'],
        },
        {
          id: 'card-atom-2',
          card_type: 'basic',
          front: '¿Qué es un Internet Gateway en OCI?',
          back: 'Un enrutador de software que provee acceso a internet para subredes públicas.',
          tags: ['oracle-cloud'],
        },
      ];
      localStorage.setItem('ankicraft_generated_cards', JSON.stringify(generatedAtomicCards));
    });

    await page.goto('/');
  });

  test('debe cargar la cola de saneamiento, mostrar estado y permitir sustitución transaccional atómica oficial', async ({
    page,
  }) => {
    // 1. Verify Sanitation Queue progress indicator is rendered
    await expect(page.locator('text=Cola Topológica')).toBeVisible();
    await expect(page.locator('text=0 / 2 saneadas')).toBeVisible();

    // 2. Verify Transactional Replace Action Bar appears for Note #201
    await expect(page.locator('text=Tarjetas Atómicas Propuestas')).toBeVisible();
    await expect(page.locator('text=Sustitución Nota #201').first()).toBeVisible();

    // 3. Click Transactional Substitution Button (Official Single Path)
    const replaceButton = page.locator('button', { hasText: /Sustituir Nota #201/i });
    await expect(replaceButton).toBeVisible();
    await replaceButton.click();

    // 4. Verify Success Toast Notification
    const toastTitle = page.locator('text=Nota #201 sustituida con éxito');
    await expect(toastTitle).toBeVisible({ timeout: 10000 });
  });
});
