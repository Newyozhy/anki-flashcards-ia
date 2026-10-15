import { test, expect } from '@playwright/test';
import { setupStandardApiMocks } from './helpers/mockApi';

test.describe('Flujo C: Deck Studio Hub, Grafo Cognitivo (DAG) y Auditoría Curricular', () => {
  test.beforeEach(async ({ page }) => {
    await setupStandardApiMocks(page);
    await page.goto('/');
  });

  test('debe abrir Deck Studio, navegar por pestañas temáticas, explorar el DAG cognitivo y cerrar con Escape', async ({
    page,
  }) => {
    // 1. Open Deck Studio from Header
    const deckStudioButton = page.locator('button', { hasText: 'Deck Studio' });
    await expect(deckStudioButton).toBeVisible();
    await deckStudioButton.click();

    // 2. Verify DeckStudioModal Dialog opens
    const studioModal = page.locator('div[role="dialog"]', { hasText: 'Deck Studio' });
    await expect(studioModal).toBeVisible();
    await expect(studioModal).toContainText('Oracle Cloud');

    // 3. Navigate to "Grafo de Calidad (DAG)" Tab
    const dagTab = studioModal.locator('button', { hasText: 'Grafo de Calidad (DAG)' });
    await dagTab.click();

    // Verify SVG DAG rendered container
    const svgDag = studioModal.locator('svg').first();
    await expect(svgDag).toBeVisible({ timeout: 10000 });

    // 4. Navigate to "Auditor de Tarjetas Malas" Tab
    const debtTab = studioModal.locator('button', { hasText: 'Auditor de Tarjetas Malas' });
    await debtTab.click();
    await expect(studioModal).toBeVisible();

    // 5. Navigate to "Expansión Topológica" Tab
    const expansionTab = studioModal.locator('button', { hasText: 'Expansión Topológica' });
    await expansionTab.click();
    await expect(studioModal).toBeVisible();

    // 6. Dismiss Deck Studio using Escape Key
    await page.keyboard.press('Escape');
    await expect(studioModal).not.toBeVisible();
  });
});
