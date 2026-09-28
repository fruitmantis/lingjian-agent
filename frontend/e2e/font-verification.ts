import { expect, type Page } from '@playwright/test';

/** Font evidence only; no business requests, system-font installation or CDN dependency. */
export async function createFontVerification(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('DOM.enable');
  await cdp.send('CSS.enable');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  const network: { url: string; status: number }[] = [];
  const blocked: string[] = [];
  await page.context().route('**/*', async route => {
    const url = new URL(route.request().url());
    if (['http:', 'https:'].includes(url.protocol) && !['127.0.0.1', 'localhost'].includes(url.hostname)) {
      blocked.push(url.origin); await route.abort();
    } else await route.continue();
  });
  page.on('response', response => {
    if (response.request().resourceType() === 'font') network.push({ url: response.url(), status: response.status() });
  });
  const pages: unknown[] = [];
  async function rendered(selector: string) {
    const { root } = await cdp.send('DOM.getDocument', { depth: -1 });
    const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector });
    return (await cdp.send('CSS.getPlatformFontsForNode', { nodeId })).fonts;
  }
  async function inspect(name: string) {
    await page.evaluate(() => document.fonts.ready);
    const fonts = await page.evaluate(() => [...document.fonts].map(f => ({ family: f.family, weight: f.weight, status: f.status })));
    expect(fonts, 'UI uses installed system fonts without web-font registration').toHaveLength(0);
    const controls = await page.evaluate(() => [...document.querySelectorAll('button,input,textarea,select,option')].map(e => ({ tag: e.tagName, className: e.className, family: getComputedStyle(e).fontFamily })));
    expect(controls.filter(c => !c.family.includes('Segoe UI')), 'Application controls inherit the shared system UI stack (excluding Next.js debug shadow DOM)').toEqual([]);
    const samples = [];
    for (const selector of ['main h1', 'main h2', 'main p', 'main button', 'main input', 'main textarea', 'main select', '[role=tab]', 'main th', 'main td']) {
      const element = page.locator(selector).first();
      if (!await element.count() || !await element.isVisible()) continue;
      const style = await element.evaluate(e => { const s = getComputedStyle(e); return { family: s.fontFamily, size: s.fontSize, weight: s.fontWeight, lineHeight: s.lineHeight, letterSpacing: s.letterSpacing, fontStyle: s.fontStyle }; });
      samples.push({ selector, style, rendered: await rendered(selector) });
    }
    const probes = [];
    for (const weight of [400,500]) for (const [kind,text] of Object.entries({ chinese: '伴飞智能体伙伴能力发展项目数据库实验案例', latin: 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz', digits: '0123456789' })) {
      await page.evaluate(({ weight, text }) => {
        const element = document.createElement('p'); element.id = 'typography-character-probe'; element.textContent = text;
        element.style.cssText = `font-family:var(--font-body);font-size:16px;font-weight:${weight};line-height:24px;letter-spacing:normal;white-space:nowrap`;
        document.body.append(element);
      }, { weight, text });
      const actual = await rendered('#typography-character-probe');
      expect(actual.length).toBeGreaterThan(0);
      expect(actual.every(f => !f.isCustomFont)).toBeTruthy();
      expect(actual.reduce((sum,f) => sum+f.glyphCount,0)).toBe(text.length);
      probes.push({ kind, weight, rendered: actual });
      await page.locator('#typography-character-probe').evaluate(e => e.remove());
    }
    expect(network, 'System fonts need no network requests').toEqual([]);
    pages.push({ name, fonts, controls, samples, probes });
  }
  return { inspect, evidence: () => ({ network, blockedOrigins: [...new Set(blocked)], externalNetworkBlocked: true, systemFonts: true, requestedWeights: [400,500], pages }) };
}
