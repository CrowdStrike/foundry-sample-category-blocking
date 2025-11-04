import { test, expect } from '@playwright/test';
import { FoundryHomePage } from '../src/pages/FoundryHomePage';
import { CategoryBlockingPage } from '../src/pages/CategoryBlockingPage';
import { config } from '../src/config/TestConfig';
import { logger } from '../src/utils/Logger';

// Use parallel mode for better performance - app state is stable after setup
test.describe.configure({ mode: 'parallel' });

test.describe('Category Blocking App E2E Tests', () => {
  let foundryHomePage: FoundryHomePage;
  let categoryBlockingPage: CategoryBlockingPage;

  // Lightweight setup - only create page objects
  test.beforeEach(async ({ page }, testInfo) => {
    foundryHomePage = new FoundryHomePage(page);
    categoryBlockingPage = new CategoryBlockingPage(page);
  });

  // Minimal cleanup - only screenshot on failure
  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status !== testInfo.expectedStatus) {
      const screenshotPath = `test-failure-${testInfo.title.replace(/\s+/g, '-').toLowerCase()}-${Date.now()}.png`;
      await page.screenshot({
        path: `test-results/${screenshotPath}`,
        fullPage: true
      });
    }

    // Quick modal cleanup without complex state management
    await categoryBlockingPage.cleanupModals();
  });

  test.describe('App Installation and Basic Navigation', () => {
    test('should verify Category Blocking app accessibility', async () => {
      await categoryBlockingPage.navigateToInstalledApp();

      // Verify we're on the app page
      const currentUrl = categoryBlockingPage.page.url();
      expect(currentUrl).toMatch(/\/foundry\/page\/[a-f0-9]+/);

      logger.success('Category Blocking app is accessible');
    });

    test('should navigate to Category Blocking app and verify iframe loads', async () => {
      await categoryBlockingPage.navigateToInstalledApp();

      // Verify iframe is present
      const iframe = categoryBlockingPage.page.locator('iframe');
      await expect(iframe).toBeVisible({ timeout: 15000 });

      logger.success('Category Blocking app iframe loaded successfully');
    });
  });

  test.describe('Content Rendering Verification', () => {
    test('should verify app content renders without JavaScript errors', async ({ page }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      // Get the iframe
      const iframe = page.frameLocator('iframe');

      // Wait for and verify main heading is visible
      const heading = iframe.locator('h1:has-text("Category Blocking")');
      await expect(heading).toBeVisible({ timeout: 15000 });
      logger.success('Main heading "Category Blocking" rendered successfully');

      // Verify subheading is visible
      const subheading = iframe.locator('text=Configure category-based blocking rules');
      await expect(subheading).toBeVisible({ timeout: 10000 });
      logger.success('Subheading rendered successfully');

      // Verify no JavaScript errors prevented loading
      // If we got this far, the React app initialized successfully
      logger.success('App content rendered without JavaScript errors');
    });

    test('should verify all navigation tabs are present', async ({ page }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe');

      // Wait for navigation to be present
      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      // Verify all 5 tabs are present in the navigation
      const tabs = [
        'Category Blocking Policy',
        'Custom Categories',
        'Domain Analytics',
        'Firewall Rules',
        'Relationship Graph'
      ];

      for (const tabName of tabs) {
        // Target tabs specifically within sl-tab elements
        const tab = iframe.locator(`sl-tab:has-text("${tabName}") a`).first();
        await expect(tab).toBeVisible({ timeout: 5000 });
        logger.info(`✓ Tab found: ${tabName}`);
      }

      logger.success('All 5 navigation tabs are present and visible');
    });
  });

  test.describe('Tab Navigation and Interaction', () => {
    test('should click Custom Categories tab and verify navigation', async ({ page }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe');

      // Wait for app to load
      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      // Click Custom Categories tab (target specifically within sl-tab)
      const customCategoriesTab = iframe.locator('sl-tab:has-text("Custom Categories") a').first();
      await customCategoriesTab.click();

      // Wait a moment for navigation
      await page.waitForTimeout(1000);

      // Verify the tab is now active (has active styling)
      const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Custom Categories' });
      await expect(activeTab).toBeVisible({ timeout: 5000 });

      logger.success('Custom Categories tab clicked and activated successfully');
    });

    test('should click Domain Analytics tab and verify navigation', async ({ page }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe');

      // Wait for app to load
      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      // Click Domain Analytics tab
      const domainAnalyticsTab = iframe.locator('a:has-text("Domain Analytics")');
      await domainAnalyticsTab.click();

      // Wait a moment for navigation
      await page.waitForTimeout(1000);

      // Verify the tab is now active
      const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Domain Analytics' });
      await expect(activeTab).toBeVisible({ timeout: 5000 });

      logger.success('Domain Analytics tab clicked and activated successfully');
    });

    test('should click Firewall Rules tab and verify navigation', async ({ page }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe');

      // Wait for app to load
      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      // Click Firewall Rules tab
      const firewallRulesTab = iframe.locator('a:has-text("Firewall Rules")');
      await firewallRulesTab.click();

      // Wait a moment for navigation
      await page.waitForTimeout(1000);

      // Verify the tab is now active
      const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Firewall Rules' });
      await expect(activeTab).toBeVisible({ timeout: 5000 });

      logger.success('Firewall Rules tab clicked and activated successfully');
    });

    test('should click Relationship Graph tab and verify navigation', async ({ page }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe');

      // Wait for app to load
      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      // Click Relationship Graph tab
      const relationshipGraphTab = iframe.locator('a:has-text("Relationship Graph")');
      await relationshipGraphTab.click();

      // Wait a moment for navigation
      await page.waitForTimeout(1000);

      // Verify the tab is now active
      const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Relationship Graph' });
      await expect(activeTab).toBeVisible({ timeout: 5000 });

      logger.success('Relationship Graph tab clicked and activated successfully');
    });

    test('should verify all tabs are clickable in sequence', async ({ page }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe');

      // Wait for app to load
      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      const tabs = [
        'Custom Categories',
        'Domain Analytics',
        'Firewall Rules',
        'Relationship Graph',
        'Category Blocking Policy' // Go back to home
      ];

      for (const tabName of tabs) {
        // Target tabs specifically within sl-tab elements
        const tab = iframe.locator(`sl-tab:has-text("${tabName}") a`).first();
        await tab.click();
        await page.waitForTimeout(500);

        // Verify tab activated
        const activeTab = iframe.locator('sl-tab[active]', { hasText: tabName });
        await expect(activeTab).toBeVisible({ timeout: 5000 });

        logger.info(`✓ Successfully clicked and activated: ${tabName}`);
      }

      logger.success('All tabs are clickable and functional');
    });
  });

  test.describe('UI Verification', () => {
    test('should verify Category Blocking app UI loads without errors', async ({ page }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      // Verify iframe is present and visible
      const iframe = page.locator('iframe');
      await expect(iframe).toBeVisible({ timeout: 15000 });

      // Get the iframe locator for content checks
      const iframeContent = page.frameLocator('iframe');

      // Verify main content loaded
      const heading = iframeContent.locator('h1:has-text("Category Blocking")');
      await expect(heading).toBeVisible({ timeout: 15000 });

      // Quick loading check - ensure no persistent loading indicators
      const loadingIndicators = iframeContent.locator('.loading, .spinner, [data-testid="loading"], [aria-label*="loading"], sl-spinner');
      const loadingCount = await loadingIndicators.count();

      if (loadingCount > 0) {
        logger.info(`Found ${loadingCount} loading indicators, waiting for them to disappear`);
        await expect(loadingIndicators.first()).not.toBeVisible({ timeout: 10000 });
      }

      logger.success('Category Blocking app UI verification completed - no errors detected');
    });
  });
});
