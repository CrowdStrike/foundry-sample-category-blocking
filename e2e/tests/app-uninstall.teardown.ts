import { test as teardown } from '@playwright/test';
import { CategoryBlockingPage } from '../src/pages/CategoryBlockingPage';

teardown('uninstall Category Blocking app', async ({ page }) => {
  const categoryBlockingPage = new CategoryBlockingPage(page);

  // Clean up by uninstalling the app after all tests complete
  await categoryBlockingPage.uninstallApp();
});