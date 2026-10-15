import { test, expect } from '@playwright/test';
import { setupStandardApiMocks } from './helpers/mockApi';

test.describe('Flujo D: Resiliencia en Runtime, Cancelación y Manejo Offline', () => {
  test.beforeEach(async ({ page }) => {
    await setupStandardApiMocks(page);
    await page.goto('/');
  });

  test('debe cancelar operaciones en vuelo al presionar Cancelar operación', async ({ page }) => {
    // Delay inspect response so we have time to cancel it
    await page.route('**/api/cards/inspect', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    // Switch to Ingest mode to access ContentDropzone
    const ingestTab = page.locator('button', { hasText: 'Ingesta Libre' });
    await ingestTab.click();

    const textTab = page.locator('button', { hasText: 'Texto / Apuntes' });
    await textTab.click();

    const textarea = page.getByRole('textbox', { name: /Texto o apuntes educativos/i });
    await textarea.fill('Texto de prueba para cancelación con AbortSignal.');

    const inspectButton = page.locator('button', { hasText: 'Analizar y Planificar' });
    await inspectButton.click();

    // Verify Cancel button appears and click it
    const cancelButton = page.locator('button', { hasText: 'Cancelar operación' });
    await expect(cancelButton).toBeVisible();
    await cancelButton.click();

    // Verify cancellation toast notification
    const cancelToast = page.locator('text=Diagnóstico cancelado por el usuario.');
    await expect(cancelToast).toBeVisible({ timeout: 5000 });
  });

  test('debe cerrar modales secundarios con la tecla Escape', async ({ page }) => {
    // Open API Key Modal
    const apiKeyButton = page.locator('button[aria-label="Configurar API Key de Gemini"]');
    await apiKeyButton.click();

    const apiKeyModal = page.locator('div[role="dialog"]', { hasText: 'Configurar Gemini API Key' });
    await expect(apiKeyModal).toBeVisible();

    // Press Escape to dismiss
    await page.keyboard.press('Escape');
    await expect(apiKeyModal).not.toBeVisible();
  });

  test('debe guiar al usuario cuando Anki Desktop falla o está inaccesible', async ({ page }) => {
    // Mock notes search failure
    await page.route('**/api/anki/decks/*/notes', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'AnkiConnect unreachable on port 8765',
        }),
      });
    });

    // Switch to Ingest mode to access ContentDropzone
    const ingestTab = page.locator('button', { hasText: 'Ingesta Libre' });
    await ingestTab.click();

    // Select Anki Card Tab
    const ankiTab = page.locator('button', { hasText: 'Tarjeta de Anki' });
    await ankiTab.click();

    // Open Card Picker
    const pickerButton = page.locator('button', { hasText: 'Abrir Explorador de Tarjetas de Anki' });
    await pickerButton.click();

    const pickerModal = page.locator('div[role="dialog"]', { hasText: 'Explorador de Tarjetas de Anki' });
    await expect(pickerModal).toBeVisible();

    // Verify troubleshooting card is displayed with port 8765 and AnkiConnect
    await expect(pickerModal).toContainText('8765');
    await expect(pickerModal).toContainText('AnkiConnect');

    // Dismiss with Escape
    await page.keyboard.press('Escape');
    await expect(pickerModal).not.toBeVisible();
  });
});
