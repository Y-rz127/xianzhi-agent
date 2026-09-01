// 一次性开发工具：调用 iztro 批量生成紫微斗数黄金快照（oracle fixtures）。
// 用途：作为 Python 自研排盘引擎 app/domain/ziwei/engine.py 的对照真值（tests/test_ziwei.py 逐组断言）。
// 本脚本及其依赖的 iztro 仅存在于 scripts/ 下（node_modules 已 gitignore），不进入生产包、不构成运行时依赖。
//
// 运行： cd scripts && node gen_ziwei_oracle.js
// 产物： ../tests/fixtures/ziwei_oracle/case_XX.json  以及 coverage.json
//
// iztro 采用默认配置（三合/全书派）：yearDivide='normal'(正月初一分界)、algorithm='default'、
// fixLeap=true（闰月上半月算本月、下半月算下月）、dayDivide='forward'（晚子时归次日起紫微）。

import { astro } from 'iztro';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(__dirname, '..', 'tests', 'fixtures', 'ziwei_oracle');
mkdirSync(outDir, { recursive: true });

astro.config({ yearDivide: 'normal', algorithm: 'default' });

// 规范化：把一宫内的星曜数组转成 {name,type,brightness,mutagen} 且按名字排序，避免 push 顺序差异。
function normStars(list) {
  return (list || [])
    .map((s) => ({ name: s.name, type: s.type, brightness: s.brightness || '', mutagen: s.mutagen || '' }))
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

function normalize(astrolabe, inputs) {
  const o = JSON.parse(JSON.stringify(astrolabe));
  return {
    inputs,
    // iztro 解析出的历法原语（供引擎桥接层逐项比对定位差异）
    primitives: {
      yearly: o.rawDates?.chineseDate?.yearly ?? o.chineseDate?.yearly ?? null,
      lunarDate: o.lunarDate,
      earthlyBranchOfSoulPalace: o.earthlyBranchOfSoulPalace,
      earthlyBranchOfBodyPalace: o.earthlyBranchOfBodyPalace,
      fiveElementsClass: o.fiveElementsClass,
      soul: o.soul,
      body: o.body,
      gender: o.gender,
    },
    // 完整命盘：十二宫（index 0 = 寅宫 … 11 = 丑宫）
    palaces: o.palaces.map((p) => ({
      index: p.index,
      name: p.name,
      heavenlyStem: p.heavenlyStem,
      earthlyBranch: p.earthlyBranch,
      isBodyPalace: !!p.isBodyPalace,
      majorStars: normStars(p.majorStars),
      minorStars: normStars(p.minorStars),
      adjectiveStars: normStars(p.adjectiveStars),
      changsheng12: p.changsheng12 || '',
      boshi12: p.boshi12 || '',
      jiangqian12: p.jiangqian12 || '',
      suiqian12: p.suiqian12 || '',
      decadal: { range: p.decadal.range, heavenlyStem: p.decadal.heavenlyStem, earthlyBranch: p.decadal.earthlyBranch },
      ages: p.ages,
    })),
  };
}

const cases = [];
function addSolar(solar, timeIndex, gender, note) {
  cases.push({ kind: 'solar', arg: [solar, timeIndex, gender, true], inputs: { calendar: 'solar', solar, timeIndex, gender, note: note || '' } });
}
function addLunar(lunar, timeIndex, gender, isLeap, note) {
  cases.push({ kind: 'lunar', arg: [lunar, timeIndex, gender, isLeap, true], inputs: { calendar: 'lunar', lunar, timeIndex, gender, isLeap, note: note || '' } });
}

// A) 覆盖十二时辰 + 男女：以 2000-08-16 为基准，逐个 timeIndex，男女交替
for (let t = 0; t <= 12; t++) {
  addSolar('2000-08-16', t, t % 2 === 0 ? '男' : '女', `时辰覆盖 index=${t}`);
}
// B) 覆盖五行局：不同日期/时辰组合，男女各若干
const grid = [
  ['1984-02-02', 0, '男'], ['1986-06-15', 3, '女'], ['1990-10-01', 6, '男'], ['1992-03-20', 9, '女'],
  ['1995-12-31', 11, '男'], ['1998-07-07', 1, '女'], ['2001-01-15', 4, '男'], ['2003-05-05', 7, '女'],
  ['2005-09-09', 2, '男'], ['2008-11-11', 5, '女'], ['2011-04-04', 8, '男'], ['2014-08-08', 10, '女'],
  ['1977-01-01', 0, '女'], ['1969-07-20', 6, '男'], ['1957-11-03', 12, '女'], ['2020-02-29', 3, '男'],
];
grid.forEach(([d, t, g]) => addSolar(d, t, g, '五行局/年代覆盖'));
// C) 闰月规则：2023 闰二月十五/十六（fixLeap=true：上半月算本月、下半月算下月），男女各一
addSolar('2023-04-05', 6, '男', '闰二月十五(归本月二月)');
addSolar('2023-04-06', 6, '女', '闰二月十六(归下月三月)');
addLunar('2023-2-15', 6, '男', true, 'lunar 闰二月十五');
addLunar('2023-2-16', 6, '女', true, 'lunar 闰二月十六');
addLunar('2023-2-15', 6, '男', false, 'lunar 非闰二月十五(对照)');
// D) 晚子时：23:30 生（timeIndex=12）与次日早子（timeIndex=0）对照，含跨年
addSolar('2025-12-31', 12, '男', '晚子时 除夕23:30');
addSolar('2026-01-01', 0, '男', '次日早子 对照');
addSolar('1999-09-08', 12, '女', '晚子时 普通日');
// E) 年分界（正月初一 vs 立春）
addSolar('2026-02-04', 5, '男', '立春当日');
addSolar('2026-02-10', 5, '女', '立春后、正月初一前(仍算上一年乙巳)');
addSolar('2026-02-16', 0, '男', '除夕早子');
addSolar('2026-02-17', 0, '女', '正月初一(丙午年起点)');
// F) 早/晚边界年
addSolar('1901-02-19', 2, '男', '早年');
addSolar('2099-12-31', 11, '女', '晚年');
// G) 农历直排若干
addLunar('1992-6-12', 4, '女', false, 'lunar 直排');
addLunar('2008-1-1', 0, '男', false, 'lunar 正月初一子时');

const written = [];
cases.forEach((c, i) => {
  const a = c.kind === 'solar' ? astro.bySolar(...c.arg) : astro.byLunar(...c.arg);
  const rec = normalize(a, c.inputs);
  const id = String(i).padStart(2, '0');
  const file = path.join(outDir, `case_${id}.json`);
  writeFileSync(file, JSON.stringify(rec, null, 2), 'utf-8');
  written.push(file);
});

// 覆盖率报告
const cov = { count: written.length, fiveElementsClass: {}, timeIndex: {}, gender: {}, leap: 0, lateZi: 0, yearlyGanzhi: {} };
written.forEach((file) => {
  const rec = JSON.parse(readFileSync(file, 'utf-8'));
  const f = cov;
  f.fiveElementsClass[rec.primitives.fiveElementsClass] = (f.fiveElementsClass[rec.primitives.fiveElementsClass] || 0) + 1;
  f.timeIndex[rec.inputs.timeIndex] = (f.timeIndex[rec.inputs.timeIndex] || 0) + 1;
  f.gender[rec.primitives.gender] = (f.gender[rec.primitives.gender] || 0) + 1;
  f.yearlyGanzhi[rec.primitives.yearly.join('')] = (f.yearlyGanzhi[rec.primitives.yearly.join('')] || 0) + 1;
  if (rec.inputs.isLeap) f.leap += 1;
  if (rec.inputs.timeIndex === 12) f.lateZi += 1;
});
writeFileSync(path.join(outDir, 'coverage.json'), JSON.stringify(cov, null, 2), 'utf-8');
console.log('generated', written.length, 'cases');
console.log('fiveElementsClass:', JSON.stringify(cov.fiveElementsClass));
console.log('timeIndex covered:', Object.keys(cov.timeIndex).map(Number).sort((a, b) => a - b).join(','));
console.log('gender:', JSON.stringify(cov.gender), '| leap:', cov.leap, '| lateZi:', cov.lateZi);
console.log('yearly ganzhi distinct:', Object.keys(cov.yearlyGanzhi).length);
