import { test, expect } from '@playwright/test';
import { setupStandardApiMocks } from './helpers/mockApi';

test.describe('Flujo A: Ingesta, Diagnóstico Pre-Flight y Generación con Auditoría', () => {
  test.beforeEach(async ({ page }) => {
    await setupStandardApiMocks(page);
    await page.goto('/');
  });

  test('debe diagnosticar material, aprobar contrato pedagógico y renderizar tarjetas con KaTeX y Cloze', async ({
    page,
  }) => {
    // 1. Verify Header Connectivity Badges
    await expect(page.locator('header')).toContainText('Conectado');
    await expect(page.locator('header')).toContainText('Gemini 3.8 Flash');

    // 2. Switch to Ingest Mode and Enter Educational Material
    const ingestTabButton = page.locator('button', { hasText: 'Ingesta Libre' });
    await ingestTabButton.click();

    const textTabButton = page.locator('button', { hasText: 'Texto / Apuntes' });
    await textTabButton.click();

    const textarea = page.getByRole('textbox', { name: /Texto o apuntes educativos/i });
    await textarea.fill(
      'Oracle Cloud Infrastructure Networking Guide: Subredes Públicas vs Privadas, Gateways y Fórmulas de Ruido.'
    );

    // 3. Trigger Pre-Flight Inspection Cockpit
    const inspectButton = page.locator('button', { hasText: 'Analizar y Planificar' });
    await expect(inspectButton).toBeEnabled();
    await inspectButton.click();

    // 4. Verify MaterialInspectionCockpit opens
    const cockpitModal = page.locator('div[role="dialog"]', {
      hasText: 'Diagnóstico Cognitivo & Andamiaje',
    });
    await expect(cockpitModal).toBeVisible();
    await expect(cockpitModal).toContainText('Arquitectura de Redes en Oracle Cloud');
    await expect(cockpitModal).toContainText('Subredes Públicas vs Privadas');
    await expect(cockpitModal).toContainText('Redes Virtuales de Nube (VCN)');

    // 5. Adjust theme card count via Stepper
    const increaseButton = cockpitModal.locator('button[aria-label*="Aumentar tarjetas"]').first();
    if (await increaseButton.isVisible()) {
      await increaseButton.click();
    }

    // 6. Approve Plan and Trigger Generation
    const approveButton = cockpitModal.locator('button', {
      hasText: /Generar .* Flashcards Aprobadas/i,
    });
    await expect(approveButton).toBeEnabled();
    await approveButton.click();

    // 7. Verify Cockpit Closes and Flashcard Grid Renders
    await expect(cockpitModal).not.toBeVisible();

    // Verify generated cards appear in the grid
    const cards = page.locator('div[id^="card-"]');
    await expect(cards).toHaveCount(2, { timeout: 15000 });

    // 8. Verify Cloze Card and KaTeX Mathematical Rendering
    const clozeCard = cards.filter({ hasText: 'Internet Gateway (IGW)' }).first();
    await expect(clozeCard).toBeVisible();

    const mathCard = cards.filter({ hasText: 'Hartley-Shannon' }).first();
    await expect(mathCard).toBeVisible();
    // KaTeX formula rendered into HTML span
    await expect(mathCard.locator('.katex')).toBeVisible();

    // 9. Verify Active Recall 3D Flip
    // Front is visible, click to flip
    const flipButton = mathCard.locator('button', { hasText: 'Ver Respuesta' });
    await flipButton.click();
    // Back content is revealed
    await expect(mathCard).toContainText('Determina la capacidad máxima en bits por segundo');

    // 10. Verify Cognitive Audit Action Bar & Modal
    const auditButton = page.locator('button', { hasText: 'Auditor Neurocognitivo' });
    await expect(auditButton).toBeVisible();
    await expect(auditButton).toContainText('95/100');
    await auditButton.click();

    const auditModal = page.locator('div[role="dialog"]', {
      hasText: 'Auditor Neurocognitivo & Linter de Calidad',
    });
    await expect(auditModal).toBeVisible();

    // Close audit modal with Escape key
    await page.keyboard.press('Escape');
    await expect(auditModal).not.toBeVisible();
  });
});
