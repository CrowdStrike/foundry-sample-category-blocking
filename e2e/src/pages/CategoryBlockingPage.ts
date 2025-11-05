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

    // Wait for iframe to be visible
    await expect(this.page.locator('iframe')).toBeVisible({ timeout: 15000 });
    this.logger.success('App iframe is visible');

    // Verify app content loaded
    const iframe = this.page.frameLocator('iframe');
    const heading = iframe.getByRole('heading', { name: /Category Blocking/i });

    await expect(heading).toBeVisible({ timeout: 10000 });
    this.logger.success('Category Blocking app loaded successfully');
  }

  /**
   * Navigate to already installed Category Blocking app
   */
  async navigateToInstalledApp(): Promise<void> {
    return this.withTiming(
      async () => {
        const appName = process.env.APP_NAME || 'foundry-sample-category-blocking';
        this.logger.info(`Navigating to installed app '${appName}'`);

        // Navigate via Custom Apps menu
        await this.navigateToPath('/foundry/home', 'Foundry home page');

        const menuButton = this.page.getByRole('button', { name: 'Menu' });
        await expect(menuButton).toBeVisible({ timeout: 10000 });
        await menuButton.click();

        const customAppsButton = this.page.getByRole('button', { name: 'Custom apps' });
        await expect(customAppsButton).toBeVisible({ timeout: 10000 });
        await customAppsButton.click();

        // Find the app button (may need to expand it)
        let appButton = this.page.getByRole('button', { name: appName, exact: true });

        try {
          await expect(appButton).toBeVisible({ timeout: 5000 });
        } catch {
          // Try partial match if exact match fails
          appButton = this.page.getByRole('button', { name: new RegExp(appName, 'i') }).first();
          await expect(appButton).toBeVisible({ timeout: 5000 });
        }

        // Click to expand if not already expanded
        if (!await appButton.getAttribute('aria-expanded')) {
          await appButton.click();
        }

        // Click the app link
        const appLink = this.page.getByRole('link', { name: new RegExp(appName, 'i') }).first();
        await expect(appLink).toBeVisible({ timeout: 5000 });
        await appLink.click();

        await this.verifyPageLoaded();
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
