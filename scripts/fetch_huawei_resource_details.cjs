/* Read details in a browser context the user has already signed into.
 * No credential export, enrollment, video playback or lab execution.
 */
const fs = require('node:fs');
const path = require('node:path');

function validateUrl(value, kind) {
  const u = new URL(value);
  const pattern = kind === 'course' ? /^\/courses\/learn\/[^/?#]+\/about$/ : /^\/lab\/experiment-detail_\d+$/;
  const host = kind === 'course' ? 'connect.huaweicloud.com' : 'edu.huaweicloud.com';
  if (u.protocol !== 'https:' || u.hostname !== host || u.username || u.password || u.port
      || u.search || u.hash || !pattern.test(u.pathname)) throw new Error('Unexpected resource URL');
  return u;
}

async function courseDetails(page, sourceUrl) {
  const expected = validateUrl(sourceUrl, 'course');
  await page.goto(sourceUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.locator('.headinggroup h2').first().waitFor({ timeout: 15000 });
  await page.locator('.html_box').first().waitFor({ timeout: 10000 });
  const actual = new URL(page.url());
  if (actual.hostname !== expected.hostname || actual.pathname !== expected.pathname) throw new Error('Course redirect or login required');
  return page.evaluate(() => {
    const text = node => node?.innerText?.trim() || '';
    const section = label => {
      const heading = [...document.querySelectorAll('.html_box .infotitle')].find(n => text(n) === label);
      if (heading) return [...heading.parentElement.children].filter(n => n !== heading).map(text).filter(Boolean).join('\n');
      // Older courses store all three sections in one rich-text HTML block.
      const lines = [...document.querySelectorAll('.html_box')].map(text).join('\n').split(/\n+/).map(s => s.trim()).filter(Boolean);
      const headings = ['课程目标', '目标学员', '课程大纲', '课程介绍', '课程简介', '先修要求'];
      const clean = line => line.replace(/[：:]$/, '').trim();
      const start = lines.findIndex(line => clean(line) === label);
      if (start < 0) return '';
      const end = lines.findIndex((line, i) => i > start && headings.includes(clean(line)));
      return lines.slice(start + 1, end < 0 ? undefined : end).join('\n');
    };
    const cover = document.querySelector('.coursename img');
    const duration = [...document.querySelectorAll('.rightInfo *')]
      .filter(n => n.children.length === 0 && /^(?:课程)?时长[：:]/.test(text(n))).map(text)[0] || '';
    return { title: text(document.querySelector('.headinggroup h2')), summary: text(document.querySelector('.coursedescription')),
      course_goals: section('课程目标'), audience: section('目标学员'), outline: section('课程大纲'),
      cover_url: cover?.src || '', duration_text: duration };
  });
}

async function labDetails(page, sourceUrl) {
  const expected = validateUrl(sourceUrl, 'lab');
  const pending = page.waitForResponse(r => {
    const u = new URL(r.url());
    return u.hostname === 'data.edu.huaweicloud.com' && u.pathname.endsWith('/sandbox/details') && r.status() === 200;
  }, { timeout: 15000 });
  pending.catch(() => {});
  await page.goto(sourceUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  const data = (await (await pending).json()).result;
  if (String(data.experiment_id) !== expected.pathname.split('_').pop() || !data.title) throw new Error('Unavailable lab or wrong ID');
  return { title: data.title, summary: data.intro || '', lab_goals: data.goal || '',
    duration_minutes: data.times > 0 ? Math.ceil(data.times / 60) : null };
}

async function captureDetails(context, manifestPath, outputPath, limit = Infinity) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const previous = fs.existsSync(outputPath) ? JSON.parse(fs.readFileSync(outputPath, 'utf8')) : { resources: [] };
  const results = new Map(previous.resources.map(r => [r.resource_id, r]));
  const save = () => {
    fs.mkdirSync(path.dirname(outputPath), { recursive: true, mode: 0o700 });
    const temp = outputPath + '.writing';
    fs.writeFileSync(temp, JSON.stringify({ captured_at: new Date().toISOString(), resources: [...results.values()] }, null, 2), { mode: 0o600 });
    fs.renameSync(temp, outputPath);
  };
  const page = await context.newPage();
  let attempted = 0;
  try {
    for (const resource of manifest.resources) {
      if (results.get(resource.resource_id)?.status === 'ok') continue;
      if (attempted++ >= limit) break;
      const kind = resource.metadata.resource_type, url = resource.metadata.source_url;
      const record = { resource_id: resource.resource_id, source_url: url, resource_type: kind };
      try {
        const details = kind === 'course' ? await courseDetails(page, url) : await labDetails(page, url);
        if (!details.title || !details.summary) throw new Error('Incomplete detail page');
        results.set(resource.resource_id, { ...record, status: 'ok', details });
      } catch {
        const login = new URL(page.url()).hostname === 'auth.huaweicloud.com';
        results.set(resource.resource_id, { ...record, status: 'unavailable', reason: login ? 'login_required' : 'detail_unavailable' });
        if (login) { save(); throw new Error('Login expired; authenticate in the original window and resume.'); }
      }
      save();
      console.log(`${results.size}/${manifest.resources.length} ${kind} ${resource.resource_id}: ${results.get(resource.resource_id).status}`);
      await page.waitForTimeout(300);
    }
  } finally { await page.close(); }
  return { captured: [...results.values()].filter(r => r.status === 'ok').length,
    unavailable: [...results.values()].filter(r => r.status !== 'ok').length };
}

module.exports = { captureDetails, courseDetails, labDetails, validateUrl };
