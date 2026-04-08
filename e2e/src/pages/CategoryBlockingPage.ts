import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Page object for Category Blocking app
 *
 * Handles navigation to the Category Blocking app
 */
export class CategoryBlockingPage extends BasePage {
  constructor(page: Page) {
    super(page, 'Category Blocking');
  }

  protected getPagePath(): string {
    // App uses dynamic foundry page URLs
    return '/foundry/page';
  }

  protected async verifyPageLoaded(): Promise<void> {
    // Verify we're on a Foundry app page
    const currentUrl = this.page.url();
    const isFoundryPage = /\/foundry\/page\/[a-f0-9]+/.test(currentUrl);

    if (!isFoundryPage) {
      throw new Error(`Expected Foundry app page URL pattern, but got: ${currentUrl}`);
    }

    this.logger.success(`Successfully navigated to Foundry app page: ${currentUrl}`);

    // Iframe sometimes doesn't render in CI. Retry with page reload.
    let iframeVisible = false;
    for (let attempt = 0; attempt < 3 && !iframeVisible; attempt++) {
      try {
        if (attempt > 0) {
          this.logger.info(`Iframe not visible, reloading page (attempt ${attempt + 1}/3)`);
          await this.page.reload({ waitUntil: 'networkidle' });
          await this.page.waitForTimeout(3000);
        }
        await expect(this.page.locator('iframe[name="portal"]')).toBeVisible({ timeout: 20000 });
        iframeVisible = true;
      } catch (e) {
        this.logger.warn(`Iframe not visible on attempt ${attempt + 1}`);
      }
    }
    if (!iframeVisible) {
      throw new Error('App iframe never appeared after 3 attempts');
    }
    this.logger.success('App iframe is visible');

    // Verify app content loaded
    const iframe = this.page.frameLocator('iframe[name="portal"]');
    const heading = iframe.getByRole('heading', { name: /Category Blocking/i });

    await expect(heading).toBeVisible({ timeout: 30000 });
    this.logger.success('Category Blocking app loaded successfully');
  }

  /**
   * Navigate to already installed Category Blocking app
   */
  async navigateToInstalledApp(): Promise<void> {
    const appName = process.env.APP_NAME || 'foundry-sample-category-blocking';

    return this.withTiming(
      async () => {
        this.logger.info(`Navigating to installed app '${appName}'`);

        // Strategy 1: Try "Open app" from the App Catalog detail page
        const openedViaCatalog = await this.tryOpenAppViaCatalog(appName);
        if (openedViaCatalog) return;

        // Strategy 2: Fall back to Custom Apps menu navigation
        this.logger.info('Falling back to Custom Apps menu navigation');
        await this.navigateToPath('/foundry/home', 'Foundry home page');
        await this.page.waitForLoadState('networkidle');

        // Retry with page refresh if Custom apps menu or app button doesn't appear
        let appFound = false;
        for (let attempt = 1; attempt <= 5; attempt++) {
          const menuButton = this.page.getByTestId('nav-trigger');
          await menuButton.waitFor({ state: 'visible', timeout: 30000 });
          await menuButton.click();
          await this.page.waitForLoadState('networkidle');

          const customAppsButton = this.page.getByRole('button', { name: 'Custom apps' });
          try {
            await customAppsButton.waitFor({ state: 'visible', timeout: 20000 });
            await customAppsButton.click();
            await this.waiter.delay(1500);
            this.logger.info(`Custom apps button found on attempt ${attempt}`);
          } catch (e) {
            this.logger.warn(`Custom apps not visible on attempt ${attempt}, refreshing page...`);
            await this.page.reload();
            await this.page.waitForLoadState('networkidle');
            await this.waiter.delay(3000);
            continue;
          }

          // Check if the app button appears in the submenu
          const appButtonCheck = this.page.getByRole('button', { name: appName, exact: false }).first();
          try {
            await appButtonCheck.waitFor({ state: 'visible', timeout: 10000 });
            appFound = true;
            this.logger.info(`App '${appName}' found in Custom apps menu on attempt ${attempt}`);
            break;
          } catch (e) {
            this.logger.warn(`App '${appName}' not in Custom apps on attempt ${attempt}, refreshing page...`);
            await this.page.reload();
            await this.page.waitForLoadState('networkidle');
            await this.waiter.delay(3000);
          }
        }
        if (!appFound) {
          throw new Error(`App '${appName}' not found in Custom apps menu after 5 attempts with page refresh`);
        }

        // Expand the app menu only if not already expanded
        const appButton = this.page.getByRole('button', { name: appName, exact: false }).first();
        await expect(appButton).toBeVisible({ timeout: 10000 });
        const isExpanded = await appButton.getAttribute('aria-expanded');
        if (isExpanded !== 'true') {
          await appButton.click();
          await this.waiter.delay(500);
        }

        // Click the app page link (scoped to this app's list to avoid ambiguity with CI app)
        const appList = this.page.getByRole('list', { name: appName, exact: true });
        const appLink = appList.getByTestId('section-link');
        await expect(appLink).toBeVisible({ timeout: 20000 });
        await this.smartClick(appLink, 'Category Blocking link');

        // Wait for navigation to app page
        await this.page.waitForURL(/\/foundry\/page\/[a-f0-9]+(\?.*)?$/, { timeout: 15000 });

        await this.verifyPageLoaded();
      },
      `Navigate to ${appName} app`
    );
  }

  /**
   * Try to open the app via the "Open app" button on its App Catalog detail page.
   * Returns true if successful, false if the button wasn't available.
   */
  private async tryOpenAppViaCatalog(appName: string): Promise<boolean> {
    try {
      this.logger.info('Trying to open app via App Catalog "Open app" button');
      const baseUrl = this.getBaseURL();
      const filterParam = encodeURIComponent(`name:~'${appName}'`);
      await this.page.goto(`${baseUrl}/foundry/app-catalog?filter=${filterParam}`);
      await this.page.waitForLoadState('domcontentloaded');

      const appLink = this.page.getByRole('link', { name: appName, exact: true });
      await appLink.waitFor({ state: 'visible', timeout: 15000 });
      await appLink.click();

      const openAppButton = this.page.getByRole('button', { name: 'Open app' });
      await openAppButton.waitFor({ state: 'visible', timeout: 10000 });

      // Set up response listener BEFORE clicking to capture the page entity response
      const pageEntityResponse = this.page.waitForResponse(
        (resp) => resp.url().includes('/api2/ui-extensions/entities/pages/v1'),
        { timeout: 15000 }
      );
      await openAppButton.click();
      this.logger.success('Clicked "Open app" button from App Catalog');

      // Wait for the page entity response and check for 404
      const response = await pageEntityResponse;
      if (response.status() === 404) {
        this.logger.warn('Page entity returned 404, retrying with reload...');
        await this.retryPageLoadAfter404();
      }

      const iframe = this.page.locator('iframe[name="portal"]');
      await iframe.waitFor({ state: 'visible', timeout: 30000 });
      await this.verifyPageLoaded();
      return true;
    } catch (e) {
      this.logger.warn(`"Open app" button not available: ${(e as Error).message}`);
      return false;
    }
  }

  /**
   * Retry page load after a 404 on the page entity endpoint.
   * The service sometimes needs a moment to register newly deployed pages.
   */
  private async retryPageLoadAfter404(maxRetries = 3): Promise<void> {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      const retryResponse = this.page.waitForResponse(
        (resp) => resp.url().includes('/api2/ui-extensions/entities/pages/v1'),
        { timeout: 15000 }
      );
      await this.page.reload();
      await this.page.waitForLoadState('domcontentloaded');

      const response = await retryResponse;
      if (response.status() !== 404) {
        this.logger.success(`Page entity returned ${response.status()} on retry ${attempt}`);
        return;
      }
      this.logger.warn(`Page entity still 404 on retry ${attempt}/${maxRetries}`);
    }
  }

  /**
   * Clean up any open modals (used in test cleanup)
   */
  async cleanupModals(): Promise<void> {
    try {
      // Quick check for any open modals and close them
      const modalCloseButtons = this.page.locator('[aria-label="Close"], button:has-text("Cancel")');
      const count = await modalCloseButtons.count();

      for (let i = 0; i < count; i++) {
        const button = modalCloseButtons.nth(i);
        if (await button.isVisible({ timeout: 1000 })) {
          await button.click();
        }
      }
    } catch (error) {
      // Ignore errors during cleanup
    }
  }

  /**
   * Create a custom category via the Custom Categories tab form.
   * Exercises the manage_category function (CustomStorage write to domain collection).
   */
  async createCustomCategory(categoryName: string, domains: string): Promise<void> {
    return this.withTiming(
      async () => {
        const iframe = this.page.frameLocator('iframe[name="portal"]');

        // Click Custom Categories tab
        const customCategoriesTab = iframe.locator('sl-tab:has-text("Custom Categories") a').first();
        await customCategoriesTab.click();
        this.logger.info('Clicked Custom Categories tab');

        // Verify tab is active
        const activeTab = iframe.locator('sl-tab[active]', { hasText: 'Custom Categories' });
        await expect(activeTab).toBeVisible({ timeout: 5000 });

        // Fill in the Category Name input
        const categoryInput = iframe.locator('input[placeholder="Enter category name"]');
        await categoryInput.waitFor({ state: 'visible', timeout: 10000 });
        await categoryInput.fill(categoryName);
        this.logger.info(`Filled category name: ${categoryName}`);

        // Fill in the Domains textarea
        const domainsTextarea = iframe.locator('textarea[placeholder*="Enter domains"]');
        await domainsTextarea.fill(domains);
        this.logger.info(`Filled domains: ${domains}`);

        // Click Create Category button
        const createButton = iframe.locator('sl-button', { hasText: 'Create Category' });
        await createButton.click({ force: true });
        this.logger.info('Clicked Create Category button');

        // Wait for sl-alert to appear in the DOM (Shoelace renders it hidden without `open`)
        const alert = iframe.locator('sl-alert');
        await alert.waitFor({ state: 'attached', timeout: 15000 });

        // Check if we got success or error
        const alertVariant = await alert.getAttribute('variant');
        const alertText = await alert.textContent() || '';
        this.logger.info(`Alert variant: ${alertVariant}, text: ${alertText.trim()}`);

        if (alertVariant === 'danger') {
          throw new Error(`Category creation failed: ${alertText.trim()}`);
        }

        this.logger.success('Custom category created successfully - CustomStorage write verified');
      },
      `Create custom category: ${categoryName}`
    );
  }
}
