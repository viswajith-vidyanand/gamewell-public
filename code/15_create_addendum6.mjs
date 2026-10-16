import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const base=process.cwd();
const dir=path.join(base,'analysis','gamewell_analysis_plan_2026-10-15');
const addPath=path.join(dir,'ADDENDUM_6_2026-10-16.md');
const manifestPath=path.join(dir,'MANIFEST_SHA256_addendum6.csv');
if(fs.existsSync(addPath)||fs.existsSync(manifestPath)) throw new Error('Target exists; refusing overwrite.');
const text=`# Addendum 6 to Analysis Plan v1 (2026-10-16)
Recorded before the bundle revision. Plan v1 and Addenda 1-5 are unchanged.
1. Descriptive aggregates (no outcome data and no exposure-outcome relationship are computed): (a) median and interquartile range of interval duration in hours in the primary valence cohort; (b) number of distinct participants across all 15,062 intervals; (c) number of distinct participants in linked intervals with life satisfaction present at both endpoints before the 48-hour limit; (d) number of distinct participants with any linked interval. They are computed from the interval dataset, saved as aggregates only, and used for the cohort flow and presentation.
2. Presentation edits to the results bundle (claims C3, C4, C8, C10, C12, new claim C13, and methods additions) were made after reviewing the first bundle draft. They change wording and rounding only; no analysis, estimate, interval or category changes.
3. Claim numbers are rounded to two decimal places; headline.json keeps full precision.
4. Ledger note: the initial 7a runs applied a 48-hour limit to cohorts defined with maximum intervals of 30h, 36h, 72h and no cutoff. Because a 48-hour limit is redundant for 30h and 36h, those two initial cohorts may equal the corrected ones; the ledger records a comparison of initial and corrected cohort counts. All four initial fits remain labelled discarded.
`;
fs.writeFileSync(addPath,text,'utf8');
const b=fs.readFileSync(addPath);
const q=x=>'"'+String(x).replaceAll('"','""')+'"';
const row=['ADDENDUM_6_2026-10-16.md',b.length,crypto.createHash('sha256').update(b).digest('hex')];
fs.writeFileSync(manifestPath,['path,bytes,sha256',row.map(q).join(',')].join('\n')+'\n','utf8');
console.log(JSON.stringify({addendum_bytes:b.length,manifest_entries:1,sha256:row[2]}));