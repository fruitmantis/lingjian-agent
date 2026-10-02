import {expect, type Page} from '@playwright/test';

export async function selectPartner(page: Page, id: string, label = '关联已有伙伴资料（可选）') {
  const input = page.getByRole('combobox', {name: label, exact: true});
  await input.click();
  await page.locator(`[role="option"][data-partner-id="${id}"]`).click();
  await expect(input).toHaveAttribute('data-partner-id', id);
}
