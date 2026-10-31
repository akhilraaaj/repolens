import { expect, test } from "@playwright/test";

test("the landing page accepts a repository and can be used from the keyboard", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /See a codebase before you read it/ })).toBeVisible();
  const input = page.getByRole("textbox", { name: "GitHub repository" });
  await input.focus();
  await expect(input).toBeFocused();
  await input.fill("vercel/swr");
  await expect(input).toHaveValue("vercel/swr");

  const heading = page.getByRole("heading", { level: 1 });
  const colors = await heading.evaluate((element) => {
    const style = getComputedStyle(element);
    return { color: style.color, background: getComputedStyle(document.body).backgroundColor };
  });
  expect(colors.color).not.toBe(colors.background);
});
