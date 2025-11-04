import { test as setup } from '@playwright/test';
import { FoundryHomePage } from '../src/pages/FoundryHomePage';
import { CategoryBlockingPage } from '../src/pages/CategoryBlockingPage';

setup('install Category Blocking app', async ({ page }) => {
  const foundryHomePage = new FoundryHomePage(page);
  const categoryBlockingPage = new CategoryBlockingPage(page);

  // Navigate to Foundry and install the app once for all tests
  await foundryHomePage.goto();
  await categoryBlockingPage.navigateToCategoryBlocking();

  // App is now installed and ready for all parallel tests
});
