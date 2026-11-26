import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

// Run against a local production build started with next start.
const origin = process.env.KUNDALI_LANDING_ORIGIN ?? "http://127.0.0.1:3102";
const screenshots = process.env.KUNDALI_LANDING_SCREENSHOTS;
const viewports = [
  { width: 1440, height: 900 },
  { width: 768, height: 1024 },
  { width: 375, height: 812 },
  { width: 320, height: 740 },
];
const landing = {
  en: { headline: "Compute first.", sample: "Synthetic sample", signIn: "Sign in", register: "Register" },
  ne: { headline: "गणना पहिले।", sample: "कृत्रिम नमुना", signIn: "साइन इन", register: "दर्ता" },
};

if (screenshots) await mkdir(screenshots, { recursive: true });
const browser = await chromium.launch();
try {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  await context.route("**/api/auth/refresh", (route) =>
    route.fulfill({ json: { authenticated: false } })
  );
  const page = await context.newPage();
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`);
  });

  for (const [locale, labels] of Object.entries(landing)) {
    const url = new URL(locale === "en" ? "/" : "/?lang=ne", origin);
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.goto(url.href);
      const content = page.locator(`#top[lang=${locale}]:visible`);
      await content.waitFor();
      await page.waitForFunction(() => document.querySelectorAll("#top").length === 1);
      await page.evaluate(() => document.fonts.ready);

      const heading = page.getByRole("heading", { level: 1 });
      assert.ok((await heading.innerText()).startsWith(labels.headline));
      assert.ok(await heading.evaluate((element) => parseFloat(getComputedStyle(element).fontSize) >= 40));
      assert.match(await page.title(), locale === "en" ? /Kundali/ : /कुण्डली/);
      assert.ok(await page.locator('meta[name="description"]').getAttribute("content"));
      assert.ok((await content.locator("figcaption").innerText()).includes(labels.sample));
      assert.equal(await content.locator("tbody tr").count(), 4);
      assert.ok((await content.locator("tbody").innerText()).includes("0.34°"));
      const image = content.locator("main img");
      await image.evaluate((element) => element.decode());
      assert.match(await image.evaluate((element) => element.currentSrc), /\/_next\/image\?/);

      const layout = await page.evaluate(() => ({
        width: document.documentElement.scrollWidth,
        clipped: [...document.querySelectorAll("header a, main a")].some((element) => {
          const { left, right } = element.getBoundingClientRect();
          return left < 0 || right > innerWidth + 1;
        }),
      }));
      assert.ok(layout.width <= viewport.width && !layout.clipped, `${locale} overflows at ${viewport.width}px`);
      if (viewport.width <= 375) {
        const undersized = await content.locator("header a, .observatory-actions a").evaluateAll(
          (links) => links.filter((link) => {
            const { width, height } = link.getBoundingClientRect();
            return height < 44 || width < 24;
          }).map((link) => link.textContent)
        );
        assert.deepEqual(undersized, [], `Undersized targets at ${viewport.width}px in ${locale}`);
      }

      if (locale === "ne" && viewport.width === 375) {
        assert.equal(await heading.locator("em").evaluate((element) =>
          getComputedStyle(element).fontStyle
        ), "normal");
        const devtools = await context.newCDPSession(page);
        await devtools.send("DOM.enable");
        await devtools.send("CSS.enable");
        const { root } = await devtools.send("DOM.getDocument");
        for (const selector of ["#observatory-title em", ".observatory-hero-copy p"]) {
          const { nodeId } = await devtools.send("DOM.querySelector", { nodeId: root.nodeId, selector });
          const { fonts } = await devtools.send("CSS.getPlatformFontsForNode", { nodeId });
          const families = fonts.filter(({ glyphCount }) => glyphCount > 0).map(({ familyName }) => familyName);
          assert.ok(families.length > 0, `No rendered fonts for ${selector}`);
          console.log(`Nepali ${selector} uses ${families.join(", ")}`);
        }
        await devtools.detach();
      }

      if (screenshots) {
        const name = `observatory-${locale}-${viewport.width}`;
        await page.screenshot({ path: path.join(screenshots, `${name}.png`), fullPage: true });
        if (viewport.width === 1440 || viewport.width === 375) {
          await page.screenshot({ path: path.join(screenshots, `${name}-hero.png`) });
        }
      }
    }

    const navigation = page.locator("#top:visible header");
    const signIn = navigation.getByRole("link", { name: labels.signIn });
    const register = navigation.getByRole("link", { name: labels.register });
    assert.equal(await signIn.getAttribute("href"), "/login");
    assert.equal(await register.getAttribute("href"), "/register");
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("href")), "#main");
    await page.keyboard.press("Enter");
    assert.equal(await page.evaluate(() => document.activeElement?.id), "main");
    await page.locator('#top:visible main a[href="#chart"]').click();
    assert.equal(new URL(page.url()).hash, "#chart");
    assert.ok(await register.evaluate((element) =>
      parseFloat(getComputedStyle(element).transitionDuration) < 0.001
    ));
  }

  await page.getByRole("link", { name: "EN", exact: true }).click();
  await page.locator('#top[lang="en"]:visible').waitFor();
  await page.getByRole("link", { name: "नेपाली", exact: true }).click();
  await page.locator('#top[lang="ne"]:visible').waitFor();
  await page.getByRole("link", { name: landing.ne.signIn }).click();
  await page.waitForURL("**/login");
  await page.goBack();
  await page.getByRole("link", { name: landing.ne.register, exact: false }).first().click();
  await page.waitForURL("**/register");
  assert.deepEqual(failures, []);
  console.log("Observatory landing passed in English and Nepali at 1440, 768, 375 and 320px.");
} finally {
  await browser.close();
}
