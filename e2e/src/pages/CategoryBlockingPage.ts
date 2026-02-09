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
        await expect(this.page.locator('iframe')).toBeVisible({ timeout: 20000 });
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
    const iframe = this.page.frameLocator('iframe');
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

        // Navigate via Custom Apps menu
        await this.navigateToPath('/foundry/home', 'Foundry home page');

        // Retry with page refresh if Custom apps menu doesn't appear
        let customAppsFound = false;
        for (let attempt = 1; attempt <= 5; attempt++) {
          const menuButton = this.page.locator('[data-test-selector="nav-trigger"]');
          await menuButton.waitFor({ state: 'visible', timeout: 30000 });
          await menuButton.click();
          await this.page.waitForLoadState('networkidle');

          const customAppsButton = this.page.getByRole('button', { name: 'Custom apps' });
          try {
            await customAppsButton.waitFor({ state: 'visible', timeout: 20000 });
            await customAppsButton.click();
            await this.page.waitForLoadState('networkidle');
            customAppsFound = true;
            this.logger.info(`Custom apps button found on attempt ${attempt}`);
            break;
          } catch (e) {
            this.logger.warn(`Custom apps not visible on attempt ${attempt}, refreshing page...`);
            await this.page.reload();
            await this.page.waitForLoadState('networkidle');
            await this.waiter.delay(3000);
          }
        }
        if (!customAppsFound) {
          throw new Error('Custom apps button not found after 5 attempts with page refresh');
        }

        // First expand the app section by clicking the button
        const appButton = this.page.getByRole('button', { name: appName, exact: false }).first();
        if (await this.elementExists(appButton, 30000)) {
          await this.smartClick(appButton, `App '${appName}' button`);

          // Now find and click the app link (displayed as "Category Blocking")
          const appLink = this.page.getByRole('link', { name: 'Category Blocking', exact: false });
          await expect(appLink).toBeVisible({ timeout: 20000 });
          await this.smartClick(appLink, 'Category Blocking link');

          // Wait for navigation to app page (URL includes query params)
          await this.page.waitForURL(/\/foundry\/page\/[a-f0-9]+(\?.*)?$/, { timeout: 15000 });

          await this.verifyPageLoaded();
        } else {
          throw new Error(`App '${appName}' not found in Custom Apps menu`);
        }
      },
      `Navigate to ${appName} app`
    );
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
}
