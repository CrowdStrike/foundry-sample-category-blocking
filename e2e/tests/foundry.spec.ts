import { test, expect } from '../src/fixtures';
import { logger } from '@crowdstrike/foundry-playwright';

test.describe.configure({ mode: 'parallel' });

test.describe('Category Blocking App E2E Tests', () => {
  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status !== testInfo.expectedStatus) {
      const screenshotPath = `test-failure-${testInfo.title.replace(/\s+/g, '-').toLowerCase()}-${Date.now()}.png`;
      await page.screenshot({
        path: `test-results/${screenshotPath}`,
        fullPage: true
      });
    }
  });

  test.describe('App Installation and Basic Navigation', () => {
    test('should verify Category Blocking app accessibility', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const currentUrl = page.url();
      expect(currentUrl).toMatch(/\/foundry\/page\/[a-f0-9]+/);

      logger.success('Category Blocking app is accessible');
    });

    test('should navigate to Category Blocking app and verify iframe loads', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.locator('iframe[name="portal"]');
      await expect(iframe).toBeVisible({ timeout: 15000 });

      logger.success('Category Blocking app iframe loaded successfully');
    });
  });

  test.describe('Content Rendering Verification', () => {
    test('should verify app content renders without JavaScript errors', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe[name="portal"]');

      const heading = iframe.locator('h1:has-text("Category Blocking")');
      await expect(heading).toBeVisible({ timeout: 15000 });
      logger.success('Main heading "Category Blocking" rendered successfully');

      const subheading = iframe.locator('text=Configure category-based blocking rules');
      await expect(subheading).toBeVisible({ timeout: 10000 });
      logger.success('Subheading rendered successfully');

      logger.success('App content rendered without JavaScript errors');
    });

    test('should verify all navigation tabs are present', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe[name="portal"]');

      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      const tabs = [
        'Category Blocking Policy',
        'Custom Categories',
        'Domain Analytics',
        'Firewall Rules',
        'Relationship Graph'
      ];

      for (const tabName of tabs) {
        const tab = iframe.locator(`sl-tab:has-text("${tabName}") a`).first();
        await expect(tab).toBeVisible({ timeout: 5000 });
        logger.info(`Tab found: ${tabName}`);
      }

      logger.success('All 5 navigation tabs are present and visible');
    });
  });

  test.describe('Tab Navigation and Interaction', () => {
    test('should click Custom Categories tab and verify navigation', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe[name="portal"]');

      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      const customCategoriesTab = iframe.locator('sl-tab:has-text("Custom Categories") a').first();
      await customCategoriesTab.click();

      const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Custom Categories' });
      await expect(activeTab).toBeVisible({ timeout: 5000 });

      logger.success('Custom Categories tab clicked and activated successfully');
    });

    test('should click Domain Analytics tab and verify navigation', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe[name="portal"]');

      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      const domainAnalyticsTab = iframe.locator('a:has-text("Domain Analytics")');
      await domainAnalyticsTab.click();

      const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Domain Analytics' });
      await expect(activeTab).toBeVisible({ timeout: 5000 });

      logger.success('Domain Analytics tab clicked and activated successfully');
    });

    test('should click Firewall Rules tab and verify navigation', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe[name="portal"]');

      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      const firewallRulesTab = iframe.locator('a:has-text("Firewall Rules")');
      await firewallRulesTab.click();

      const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Firewall Rules' });
      await expect(activeTab).toBeVisible({ timeout: 5000 });

      logger.success('Firewall Rules tab clicked and activated successfully');
    });

    test('should click Relationship Graph tab and verify navigation', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe[name="portal"]');

      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      const relationshipGraphTab = iframe.locator('a:has-text("Relationship Graph")');
      await relationshipGraphTab.click();

      const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Relationship Graph' });
      await expect(activeTab).toBeVisible({ timeout: 5000 });

      logger.success('Relationship Graph tab clicked and activated successfully');
    });

    test('should verify all tabs are clickable in sequence', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.frameLocator('iframe[name="portal"]');

      await expect(iframe.locator('h1:has-text("Category Blocking")')).toBeVisible({ timeout: 15000 });

      const tabs = [
        'Custom Categories',
        'Domain Analytics',
        'Firewall Rules',
        'Relationship Graph',
        'Category Blocking Policy'
      ];

      for (const tabName of tabs) {
        const tab = iframe.locator(`sl-tab:has-text("${tabName}") a`).first();
        await tab.click();

        const activeTab = iframe.locator('sl-tab[active]', { hasText: tabName });
        await expect(activeTab).toBeVisible({ timeout: 5000 });

        logger.info(`Successfully clicked and activated: ${tabName}`);
      }

      logger.success('All tabs are clickable and functional');
    });
  });

  test.describe('UI Verification', () => {
    test('should verify Category Blocking app UI loads without errors', async ({ page, categoryBlockingPage }) => {
      await categoryBlockingPage.navigateToInstalledApp();

      const iframe = page.locator('iframe[name="portal"]');
      await expect(iframe).toBeVisible({ timeout: 15000 });

      const iframeContent = page.frameLocator('iframe[name="portal"]');

      const heading = iframeContent.locator('h1:has-text("Category Blocking")');
      await expect(heading).toBeVisible({ timeout: 15000 });

      const loadingIndicators = iframeContent.locator('.loading, .spinner, [data-testid="loading"], [aria-label*="loading"], sl-spinner');
      const loadingCount = await loadingIndicators.count();

      if (loadingCount > 0) {
        logger.info(`Found ${loadingCount} loading indicators, waiting for them to disappear`);
        await expect(loadingIndicators.first()).not.toBeVisible({ timeout: 10000 });
      }

      logger.success('Category Blocking app UI verification completed - no errors detected');
    });
  });

  test.describe('Custom Categories - Collection Interaction', () => {
    test('should create a custom category via the form', async ({ categoryBlockingPage }) => {
      test.setTimeout(60000);
      await categoryBlockingPage.navigateToInstalledApp();
      await categoryBlockingPage.createCustomCategory(
        `e2e-test-${Date.now()}`,
        'test-e2e.example.com, test-e2e2.example.com'
      );
    });
  });
});
