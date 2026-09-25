/* One-off public catalog capture. No login, learning enrollment or lab execution. */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('../frontend/node_modules/playwright');

const directory = process.argv[2];
if (!directory) throw new Error('Usage: node scripts/fetch_huawei_resources.cjs <output-directory> [--reuse]');
const reuse = process.argv.includes('--reuse');
const pages = {
  roles: 'https://www.huaweicloud.com/partners/support/learningpath-servicepartner.html',
  codearts: 'https://www.huaweicloud.com/partners/training/learningpath-codearts.html',
  modelarts: 'https://www.huaweicloud.com/partners/training/learningpath-modelarts.html',
  dataarts: 'https://www.huaweicloud.com/partners/training/learningpath-dataarts.html',
  agentarts: 'https://www.huaweicloud.com/partners/training/learningpath-agentarts.html',
  labs: 'https://www.huaweicloud.com/partners/training/lab-environment.html',
};
const zones = { codearts: 'CodeArts', modelarts: 'ModelArts', dataarts: 'DataArts', agentarts: 'AgentArts' };
const save = (name, value) => fs.writeFileSync(path.join(directory, name), JSON.stringify(value, null, 2), { mode: 0o600 });

(async () => {
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const browser = await chromium.launch({ headless: true });
  const entries = [], skipped = [];
  try {
    const page = await browser.newPage();
    for (const [name, url] of Object.entries(pages)) {
      const cache = path.join(directory, `${name}.html`);
      if (reuse && fs.existsSync(cache)) {
        await page.route('**/*', route => route.abort());
        await page.setContent(fs.readFileSync(cache, 'utf8'), { waitUntil: 'domcontentloaded' });
      } else {
        await page.unroute('**/*');
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await page.locator(name === 'labs' ? 'textarea.cardContents-visible-data' : '.product-content a.card').first().waitFor();
        fs.writeFileSync(cache, await page.content(), { mode: 0o600 });
      }
      const extracted = await page.evaluate(() => {
        const text = (node, selector) => node.querySelector(selector)?.textContent?.trim() || '';
        return {
          cards: [...document.querySelectorAll('.product-content a.card[href]')].map(a => ({
            source_url: a.getAttribute('href'), title: text(a, '.card-logo-title') || text(a, '.card-title'),
            summary: text(a, '.card-description'), tags: text(a, '.card-tags'),
            group: text(a.closest('.first-content'), '.first-title'),
            level: a.closest('.second-flex') ? text(a.closest('.second-flex'), '.second-title') : '',
          })),
          labs: [...document.querySelectorAll('textarea.cardContents-visible-data')].flatMap(t => JSON.parse(t.value)),
        };
      });
      if (name !== 'labs' && !extracted.cards.length) throw new Error(`No course cards: ${name}`);
      for (const card of extracted.cards) {
        let url;
        try { url = new URL(card.source_url.trim()); } catch { /* recorded below */ }
        const valid = url?.protocol === 'https:' && url?.hostname === 'connect.huaweicloud.com'
          && !url.username && !url.password && !url.port
          && /^\/courses\/learn\/[^/?#]+\/about\/?$/.test(url.pathname)
          && !/考试/.test(card.tags);
        if (!valid) {
          skipped.push({ title: card.title, reason: /考试/.test(card.tags) || url?.pathname.includes('/exam/')
            ? 'exam_not_course' : 'invalid_course_link', source_page: pages[name] });
          continue;
        }
        // Course IDs live in the path. Never retain source-site SSO tickets/tracking parameters.
        card.source_url = url.origin + url.pathname.replace(/\/$/, '');
        // Mobile cards repeat desktop cards without the level heading.
        if (name === 'roles' && !card.level) continue;
        entries.push({ resource_type: 'course', title: card.title, summary: card.summary, source_url: card.source_url,
          roles: name === 'roles' ? [card.group] : [], zones: zones[name] ? [zones[name]] : [],
          source_level: card.level || card.group, source_page: pages[name] });
      }
      for (const row of extracted.labs) {
        const c = row.context;
        const tags = [...new Set([...(row.filter.tags || []), ...(c.cardTags || [])].map(t => t.trim()))];
        entries.push({ resource_type: 'lab', title: c.title, summary: c.description, source_url: c.cardHref,
          roles: tags.filter(t => t.endsWith('工程师')), zones: tags.filter(t => Object.values(zones).includes(t)),
          source_level: c.cardTagsColorful?.[0]?.tagText || '',
          duration_text: c.advantages?.find(a => a.iconType === 'time')?.text || '', source_page: url });
      }
      console.log(`${name}: ${extracted.cards.length} cards, ${extracted.labs.length} labs`);
    }
    await page.close();
    const detailsFile = path.join(directory, 'lab-details.json');
    const details = reuse && fs.existsSync(detailsFile) ? JSON.parse(fs.readFileSync(detailsFile, 'utf8')) : {};
    const labPage = await browser.newPage();
    for (const entry of entries.filter(e => e.resource_type === 'lab')) {
      if (details[entry.source_url]?.verified) continue;
      if (!/^https:\/\/edu\.huaweicloud\.com\/lab\/experiment-detail_\d+$/.test(entry.source_url)) throw new Error('Unexpected lab URL');
      try {
        const response = labPage.waitForResponse(r => new URL(r.url()).hostname === 'data.edu.huaweicloud.com'
          && new URL(r.url()).pathname.endsWith('/sandbox/details') && r.status() === 200, { timeout: 20000 });
        // Consume rejection even if navigation itself fails.
        response.catch(() => {});
        await labPage.goto(entry.source_url, { waitUntil: 'domcontentloaded', timeout: 30000 });
        const data = (await (await response).json()).result;
        if (String(data.experiment_id) !== entry.source_url.split('_').pop()) throw new Error('Detail ID mismatch');
        details[entry.source_url] = { verified: true, title: data.title, summary: data.intro,
          lab_goals: data.goal || '', duration_seconds: data.times, source_level: data.diff };
        console.log(`lab ${data.experiment_id}: verified`);
      } catch (error) {
        details[entry.source_url] = { verified: false, reason: 'public_detail_unavailable' };
        console.log(`lab ${entry.source_url.split('_').pop()}: detail unavailable`);
      }
      save('lab-details.json', details);
    }
    for (const entry of entries) if (details[entry.source_url]) entry.detail = details[entry.source_url];
    save('catalog.json', { captured_at: new Date().toISOString(), pages, entries, skipped });
    console.log(`Saved ${entries.length} source occurrences; deduplication happens before import.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
