/* Offline DOM/API fixtures only; no real site or account access. */
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('../frontend/node_modules/playwright');
const { courseDetails, labDetails, validateUrl } = require('./fetch_huawei_resource_details.cjs');
let browser;
before(async () => { browser = await chromium.launch({ headless: true }); });
after(async () => { await browser.close(); });
const source = 'https://connect.huaweicloud.com/courses/learn/C123/about';
const shell = body => `<div class="headinggroup"><h2>官方课程</h2></div>
 <div class="coursedescription">完整简介</div><div class="coursename"><img src="https://edu-res.hc-cdn.cn/a.jpg"></div>${body}`;

async function readCourse(html) {
  const page = await browser.newPage();
  try {
    await page.route('**/*', route => route.request().url() === source
      ? route.fulfill({ contentType: 'text/html; charset=utf-8', body: shell(html) }) : route.abort());
    return await courseDetails(page, source);
  } finally { await page.close(); }
}

test('separate section blocks preserve goals, audience and outline', async () => {
  const details = await readCourse('<div class="html_box"><div class="infotitle">课程目标</div><p>目标一</p><p>目标二</p></div>'
    + '<div class="html_box"><div class="infotitle">目标学员</div><p>工程师</p></div>'
    + '<div class="html_box"><div class="infotitle">课程大纲</div><p>第一章</p><p>第二章</p></div>');
  assert.equal(details.title, '官方课程');
  assert.equal(details.course_goals, '目标一\n目标二');
  assert.equal(details.audience, '工程师');
  assert.equal(details.outline, '第一章\n第二章');
  assert.equal(details.cover_url, 'https://edu-res.hc-cdn.cn/a.jpg');
  assert.equal(details.duration_text, '');
});

test('legacy rich-text headings remain separate, without inventing missing fields', async () => {
  const details = await readCourse('<div class="html_box"><p>课程目标：</p><p>学习迁移</p>'
    + '<p>目标学员</p><p>交付工程师</p><p>课程大纲</p><p>评估</p><p>迁移</p><p>先修要求</p><p>基础知识</p></div>');
  assert.equal(details.course_goals, '学习迁移');
  assert.equal(details.audience, '交付工程师');
  assert.equal(details.outline, '评估\n迁移');
  assert.equal((await readCourse('<div class="html_box">只有简介</div>')).outline, '');
});

test('lab data is verified against the source ID and whitelisted', async () => {
  const page = await browser.newPage();
  const api = 'https://data.edu.huaweicloud.com/service/sandbox/details';
  let experiment_id = '123';
  try {
    await page.route('**/*', route => route.request().url() === api
      ? route.fulfill({ contentType: 'application/json', body: JSON.stringify({ result: {
          experiment_id, title: '官方实验', intro: '简介', goal: '目标与要求', times: 3601, price: 99, num: 100,
        } }) })
      : route.fulfill({ contentType: 'text/html; charset=utf-8', body: `<script>fetch('${api}')</script>` }));
    const url = 'https://edu.huaweicloud.com/lab/experiment-detail_123';
    assert.deepEqual(await labDetails(page, url), {
      title: '官方实验', summary: '简介', lab_goals: '目标与要求', duration_minutes: 61,
    });
    experiment_id = '999';
    await assert.rejects(labDetails(page, url), /wrong ID/);
  } finally { await page.close(); }
});

test('credential-bearing, unrelated and non-detail URLs are rejected', () => {
  for (const url of [source + '?ticket=secret', source + '#details', source.replace('connect.', 'fake.'),
    source.replace('https://', 'https://user:password@'), source.replace('/learn/', '/exam/')]) {
    assert.throws(() => validateUrl(url, 'course'));
  }
});
