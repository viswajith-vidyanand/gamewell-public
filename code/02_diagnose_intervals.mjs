// Independent, aggregate-only diagnostics for the existing GameWell interval file.
// Node built-ins only. This script does not import or reuse build_intervals.mjs.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const outDir = path.dirname(new URL(import.meta.url).pathname.replace(/^\//, '').replaceAll('%20', ' '));
const root = path.resolve(outDir, '..', '..');
const inputDir = path.join(root, 'analysis', 'gamewell_interval_dataset_2026-10-15');
const inputFile = path.join(inputDir, 'gamewell_daily_intervals.csv.gz');
const expectedFiles = ['gamewell_daily_intervals.csv.gz', 'data_dictionary.csv', 'build_intervals.mjs'];
for (const f of expectedFiles) if (!fs.existsSync(path.join(inputDir, f))) throw new Error(`Missing required input ${f}`);
const csv = (s) => {
  const rows=[]; let row=[], cell='', quoted=false;
  for(let i=0;i<s.length;i++){const c=s[i]; if(quoted){if(c==='"'&&s[i+1]==='"'){cell+='"';i++;}else if(c==='"')quoted=false;else cell+=c;}else if(c==='"')quoted=true;else if(c===','){row.push(cell);cell='';}else if(c==='\n'){row.push(cell.replace(/\r$/,''));rows.push(row);row=[];cell='';}else cell+=c;}
  if(cell.length||row.length){row.push(cell.replace(/\r$/,''));rows.push(row);} const h=rows.shift(); return rows.filter(r=>r.length===h.length).map(r=>Object.fromEntries(h.map((k,i)=>[k,r[i]])));
};
const rows=csv(zlib.gunzipSync(fs.readFileSync(inputFile)).toString('utf8'));
const n=x=>x===''||x==null?null:(Number.isFinite(Number(x))?Number(x):null);
const b=x=>x==='true'?true:x==='false'?false:null;
const quant=(a,p)=>{if(!a.length)return null;const x=[...a].sort((u,v)=>u-v),h=(x.length-1)*p,i=Math.floor(h);return x[i]+(x[Math.min(i+1,x.length-1)]-x[i])*(h-i);};
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:null;
const sd=a=>a.length>1?Math.sqrt(a.reduce((s,x)=>s+(x-mean(a))**2,0)/(a.length-1)):null;
const summary=(a)=>({n:a.length,mean:mean(a),sd:sd(a),min:quant(a,0),q05:quant(a,.05),q25:quant(a,.25),median:quant(a,.5),q75:quant(a,.75),q95:quant(a,.95),max:quant(a,1)});
const write=(name, objects)=>{const keys=[...new Set(objects.flatMap(o=>Object.keys(o)))];const val=x=>x==null?'':String(x).replaceAll('"','""');const body=[keys.join(','),...objects.map(o=>keys.map(k=>`"${val(o[k])}"`).join(','))].join('\n')+'\n';fs.writeFileSync(path.join(outDir,name),body,'utf8');};
const finite=(field, subset=rows)=>subset.map(r=>n(r[field])).filter(x=>x!==null);
const linked=r=>b(r.xbox_linked)===true||b(r.nintendo_linked)===true;
const validTs=x=>typeof x==='string'&&/(Z|[+-]\d{2}:?\d{2})$/i.test(x)&&Number.isFinite(Date.parse(x));
const valid=rows.filter(r=>r.timestamp_status==='valid');
const linkedRows=rows.filter(linked);
const ids=new Set(linkedRows.map(r=>r.participant_id));
const duplicates=rows.length-new Set(rows.map(r=>`${r.participant_id}\u0000${r.interval_start_utc}`)).size;
const durations=rows.map(r=>n(r.interval_duration_minutes));
const exposure=rows.map(r=>n(r.recorded_linked_console_minutes_unique));
const missingMismatch=rows.filter((r,i)=>linked(r)===(exposure[i]===null));
const unmatched=rows.filter(r=>r.participant_linkage_status==='intake_missing');
const ratios=linkedRows.map(r=>n(r.recorded_linked_console_minutes_unique)/n(r.interval_duration_minutes)).filter(Number.isFinite);
const checks=[
 ['total_rows',rows.length,15062],['linked_console_intervals',linkedRows.length,5904],['participants_with_linked_intervals',ids.size,419],
 ['duplicate_participant_interval_start_rows',duplicates,0],['nonpositive_or_missing_durations',durations.filter(x=>x===null||x<=0).length,0],
 ['invalid_or_nonexplicit_timestamp_rows',rows.filter(r=>!validTs(r.interval_start_utc)||!validTs(r.interval_end_utc)).length,0],
 ['exposure_linkage_missingness_mismatches',missingMismatch.length,0],['intake_missing_intervals_with_missing_exposure',unmatched.filter(r=>n(r.recorded_linked_console_minutes_unique)===null).length,unmatched.length],
 ['linked_exposure_exceeds_interval_minutes',linkedRows.filter(r=>n(r.recorded_linked_console_minutes_unique)>n(r.interval_duration_minutes)+1e-6).length,0],
 ['max_exposure_duration_ratio',Math.max(...ratios),'< = 1'],['affect_complete_endpoint_pairs',linkedRows.filter(r=>n(r.prior_affective_valence)!==null&&n(r.later_affective_valence)!==null).length,5774],
 ['life_satisfaction_complete_endpoint_pairs',linkedRows.filter(r=>n(r.prior_life_satisfaction)!==null&&n(r.later_life_satisfaction)!==null).length,5769],
 ['both_outcomes_complete_endpoint_pairs',linkedRows.filter(r=>['prior_affective_valence','later_affective_valence','prior_life_satisfaction','later_life_satisfaction'].every(k=>n(r[k])!==null)).length,5761]
].map(([check,observed,expected])=>({check,observed,expected,pass:check==='max_exposure_duration_ratio'?observed<=1+1e-9:observed===expected}));
write('integrity_checks.csv',checks);

const completeBoth=linkedRows.filter(r=>['prior_affective_valence','later_affective_valence','prior_life_satisfaction','later_life_satisfaction'].every(k=>n(r[k])!==null));
const participantsOf=sub=>new Set(sub.map(r=>r.participant_id));
function icc(field,sub){const g=new Map();for(const r of sub){if(!g.has(r.participant_id))g.set(r.participant_id,[]);g.get(r.participant_id).push(n(r[field]));}const sets=[...g.values()],N=sets.reduce((s,a)=>s+a.length,0),k=sets.length,grand=mean(sets.flat());let ssb=0,ssw=0,sq=0;for(const a of sets){const m=mean(a);ssb+=a.length*(m-grand)**2;ssw+=a.reduce((s,x)=>s+(x-m)**2,0);sq+=a.length*a.length;}const msb=ssb/(k-1),msw=ssw/(N-k),n0=(N-sq/N)/(k-1),vb=Math.max(0,(msb-msw)/n0),icc=vb/(vb+msw);return {participants:k,intervals:N,method_of_moments_ICC_1:icc,between_variance_component:vb,within_variance_component:msw,raw_untruncated_between_component:(msb-msw)/n0};}
function withinCorr(prior,later,sub){const g=new Map();for(const r of sub){if(!g.has(r.participant_id))g.set(r.participant_id,[]);g.get(r.participant_id).push([n(r[prior]),n(r[later])]);}const usable=[...g.values()].filter(a=>a.length>=2);let xx=0,yy=0,xy=0;for(const a of usable){const mx=mean(a.map(x=>x[0])),my=mean(a.map(x=>x[1]));for(const [x,y] of a){xx+=(x-mx)**2;yy+=(y-my)**2;xy+=(x-mx)*(y-my);}}return {participants:usable.length,intervals:usable.reduce((s,a)=>s+a.length,0),within_person_centered_r:xy/Math.sqrt(xx*yy)};}
const outcomeRows=[];
for(const [measure,field] of [['affective_valence','later_affective_valence'],['life_satisfaction','later_life_satisfaction']]){const a=completeBoth.map(r=>n(r[field]));const s=summary(a);outcomeRows.push({measure,endpoint:'later_survey',...s,floor_value:1,floor_count:a.filter(x=>x===1).length,ceiling_value:100,ceiling_count:a.filter(x=>x===100).length,participants:participantsOf(completeBoth).size,analysis_intervals:a.length,selection:'linked intervals complete for both measures at both endpoints'});}
write('outcome_distributions.csv',outcomeRows);
const outcomeBins=[];
for(const [measure,field] of [['affective_valence','later_affective_valence'],['life_satisfaction','later_life_satisfaction']]) for(let lo=0;lo<100;lo+=10){const hi=lo+9;outcomeBins.push({measure,bin:`${lo}-${hi}`,count:completeBoth.filter(r=>{const x=n(r[field]);return x>=lo&&x<=hi;}).length});}
write('outcome_plot_bins.csv',outcomeBins);
write('outcome_repeated_structure.csv',[
 {measure:'affective_valence',statistic:'later-scores ICC(1), one-way random-intercept method of moments',...icc('later_affective_valence',completeBoth)},
 {measure:'affective_valence',statistic:'within-person centered prior-to-later correlation',...withinCorr('prior_affective_valence','later_affective_valence',completeBoth)},
 {measure:'life_satisfaction',statistic:'later-scores ICC(1), one-way random-intercept method of moments',...icc('later_life_satisfaction',completeBoth)},
 {measure:'life_satisfaction',statistic:'within-person centered prior-to-later correlation',...withinCorr('prior_life_satisfaction','later_life_satisfaction',completeBoth)}
]);

const linkedExp=linkedRows.map(r=>n(r.recorded_linked_console_minutes_unique));
const rates=linkedRows.map(r=>n(r.recorded_linked_console_minutes_unique)/(n(r.interval_duration_minutes)/60));
const gpid=new Map();for(const r of linkedRows){if(!gpid.has(r.participant_id))gpid.set(r.participant_id,[]);gpid.get(r.participant_id).push(n(r.recorded_linked_console_minutes_unique));}
const personMean=[...gpid.values()].map(mean),personSd=[...gpid.values()].map(sd).filter(Number.isFinite);
const varying=[...gpid.values()].filter(a=>a.length>1&&Math.max(...a)-Math.min(...a)>1e-6).length;
const mixed=[...gpid.values()].filter(a=>a.some(x=>x===0)&&a.some(x=>x>0)).length;
function rank(a){const order=a.map((v,i)=>[v,i]).sort((x,y)=>x[0]-y[0]),out=Array(a.length);for(let i=0;i<order.length;){let j=i+1;while(j<order.length&&order[j][0]===order[i][0])j++;for(let k=i;k<j;k++)out[order[k][1]]=(i+j-1)/2+1;i=j;}return out;}
const dur=linkedRows.map(r=>n(r.interval_duration_minutes));const rx=rank(dur),ry=rank(linkedExp);const rho=rx.reduce((s,x)=>s+(x-mean(rx))*(ry[rx.indexOf(x)]||0),0); // replaced below by paired covariance
let rxy=0,rxx=0,ryy=0;for(let i=0;i<rx.length;i++){rxy+=(rx[i]-mean(rx))*(ry[i]-mean(ry));rxx+=(rx[i]-mean(rx))**2;ryy+=(ry[i]-mean(ry))**2;}
const expSummary=[{measure:'unique linked-console minutes per interval',...summary(linkedExp),zero_count:linkedExp.filter(x=>x===0).length,zero_share:linkedExp.filter(x=>x===0).length/linkedExp.length,participants:ids.size,intervals:linkedRows.length},{measure:'unique linked-console minutes per interval hour',...summary(rates),zero_count:rates.filter(x=>x===0).length,zero_share:rates.filter(x=>x===0).length/rates.length,participants:ids.size,intervals:linkedRows.length},
 {measure:'participant-specific mean interval minutes; distribution across participants',...summary(personMean),zero_count:null,zero_share:null,participants:personMean.length,intervals:linkedRows.length},
 {measure:'participant-specific within-person SD interval minutes; distribution across participants with >=2 intervals',...summary(personSd),zero_count:null,zero_share:null,participants:personSd.length,intervals:linkedRows.length},
 {measure:'exposure vs interval duration; Spearman rank correlation',n:linkedRows.length,participants:ids.size,spearman_rho:rxy/Math.sqrt(rxx*ryy),zero_count:null,zero_share:null}];
write('exposure_summary.csv',expSummary);
const expBins=[['0',x=>x===0],['>0-30',x=>x>0&&x<=30],['>30-60',x=>x>30&&x<=60],['>60-120',x=>x>60&&x<=120],['>120-240',x=>x>120&&x<=240],['>240-480',x=>x>240&&x<=480],['>480',x=>x>480]];
write('exposure_plot_bins.csv',expBins.map(([bin,test])=>({bin,count:linkedExp.filter(test).length})));
function histogramSvg(title,groups,file){const width=760,height=360,left=60,bottom=55,top=40,usableH=height-top-bottom,usableW=width-left-25,max=Math.max(...groups.map(g=>g.count),1),bar=usableW/groups.length*.72,gap=usableW/groups.length;let bars='';groups.forEach((g,i)=>{const h=g.count/max*usableH,x=left+i*gap+(gap-bar)/2,y=top+usableH-h;bars+=`<rect x="${x}" y="${y}" width="${bar}" height="${h}" fill="#3b82a0"/><text x="${x+bar/2}" y="${height-30}" text-anchor="middle" font-size="11">${g.bin}</text><text x="${x+bar/2}" y="${y-5}" text-anchor="middle" font-size="10">${g.count}</text>`;});const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="white"/><text x="${width/2}" y="24" text-anchor="middle" font-family="sans-serif" font-size="16">${title}</text><line x1="${left}" y1="${top+usableH}" x2="${width-25}" y2="${top+usableH}" stroke="#333"/>${bars}<text x="${width/2}" y="${height-6}" text-anchor="middle" font-family="sans-serif" font-size="12">Aggregate bins; count labels shown</text></svg>`;fs.writeFileSync(path.join(outDir,file),svg,'utf8');}
histogramSvg('Later affective valence (linked intervals, complete on both outcomes)',outcomeBins.filter(x=>x.measure==='affective_valence'),'affective_valence_histogram.svg');
histogramSvg('Later life satisfaction (linked intervals, complete on both outcomes)',outcomeBins.filter(x=>x.measure==='life_satisfaction'),'life_satisfaction_histogram.svg');
histogramSvg('Unique linked-console minutes per interval',expBins.map(([bin,test])=>({bin,count:linkedExp.filter(test).length})),'console_minutes_histogram.svg');
write('exposure_linkage_groups.csv',['xbox_only','nintendo_only','xbox_and_nintendo'].map(group=>{const a=linkedRows.filter(r=>r.participant_linkage_status===group),v=a.map(r=>n(r.recorded_linked_console_minutes_unique));return {linkage_group:group,participants:new Set(a.map(r=>r.participant_id)).size,intervals:a.length,zero_intervals:v.filter(x=>x===0).length,zero_share:v.filter(x=>x===0).length/a.length};}));
write('exposure_variation.csv',[{measure:'participants with both zero and positive exposure intervals',count:mixed,participants_with_linked_intervals:ids.size},{measure:'participants with within-person exposure variation across >=2 linked intervals',count:varying,participants_with_linked_intervals:ids.size}]);

const cutoffs=[30,36,48,72,Infinity];
write('gap_cutoff_counts.csv',cutoffs.map(c=>{const label=Number.isFinite(c)?`${c}_hours`:'no_cutoff';const all=linkedRows.filter(r=>n(r.interval_duration_hours)<=c);const comp=all.filter(r=>['prior_affective_valence','later_affective_valence','prior_life_satisfaction','later_life_satisfaction'].every(k=>n(r[k])!==null));const counts=new Map();for(const r of all)counts.set(r.participant_id,(counts.get(r.participant_id)||0)+1);const cc=new Map();for(const r of comp)cc.set(r.participant_id,(cc.get(r.participant_id)||0)+1);const by=new Map();for(const r of comp){if(!by.has(r.participant_id))by.set(r.participant_id,[]);by.get(r.participant_id).push(n(r.recorded_linked_console_minutes_unique));}const ncounts=[...counts.values()],cv=[...by.values()];return {maximum_interval_length:label,linked_intervals_retained:all.length,participants_with_at_least_2_complete_intervals:[...cc.values()].filter(x=>x>=2).length,participants_with_at_least_5_complete_intervals:[...cc.values()].filter(x=>x>=5).length,participants_with_repeated_exposure_variation:cv.filter(a=>a.length>=2&&Math.max(...a)-Math.min(...a)>1e-6).length,participants_with_both_zero_and_positive:cv.filter(a=>a.includes(0)&&a.some(x=>x>0)).length,median_linked_intervals_per_participant:quant(ncounts,.5),q25_linked_intervals_per_participant:quant(ncounts,.25),q75_linked_intervals_per_participant:quant(ncounts,.75),participants_with_retained_intervals:counts.size,complete_both_outcome_intervals:comp.length};}));

const codeRows=[
 ['data-process.qmd','20-27','raw daily/telemetry timestamp import','read_csv with type inference; no timezone option specified.'],
 ['index.qmd','229-240','clean daily/Xbox/Nintendo timestamp import','read_csv with type inference; no timezone option specified.'],
 ['build_intervals.mjs','101-107','parseUtc','Explicit Z/offset required; Date.parse interprets offset/Z as instant; local timestamps rejected.'],
 ['build_intervals.mjs','156','daily row date','Daily survey date passed to parseUtc; instant interpretation.'],
 ['build_intervals.mjs','176-177','clean session start/end','Both endpoints passed to parseUtc; same UTC instant basis as survey dates.'],
 ['build_intervals.mjs','521-523','input source timestamp suffix checks','Build validation checks daily, Xbox, and Nintendo source rows for Z suffix; report documents source Z/explicit-offset expectation.'],
 ['R/helpers.R','194-195','session_start/session_end in merge_adjacent_sessions','as.POSIXct(..., tz="UTC").'],
 ['R/helpers.R','245-246','session_start/session_end in resolve_overlaps','as.POSIXct(..., tz="UTC").'],
 ['data-process.qmd','474','daily survey date to baseline_day/hour','as.Date(date), hour(date); no participant timezone conversion at this point.'],
 ['data-process.qmd','279-307','telemetry local-time conversion','UTC telemetry adjusted using timezone/DST helper for local calendar aggregation.'],
 ['index.qmd','259','intake date','as_datetime(date, tz="UTC").'],
 ['index.qmd','266','Steam timestamp','as_datetime(timestamp, tz="UTC").'],
 ['index.qmd','314-365','telemetry local-time conversion','UTC telemetry converted to local hour using timezone/DST offset.'],
 ['index.qmd','1900-1941','daily survey and session display window','as.POSIXct without explicit tz for local windows and survey date; code comments call survey timestamp already local. This display path differs from interval builder.']
].map(([file,line_ref,field,treatment])=>({file,line_ref,field,treatment}));write('timestamp_audit.csv',codeRows);
const dict=csv(fs.readFileSync(path.join(inputDir,'data_dictionary.csv'),'utf8'));
const required=['participant_id','interval_start_utc','interval_end_utc','interval_duration_minutes','interval_duration_hours','prior_affective_valence','later_affective_valence','prior_life_satisfaction','later_life_satisfaction','xbox_linked','nintendo_linked','participant_linkage_status','recorded_linked_console_minutes_unique'];
write('dictionary_coverage.csv',required.map(variable=>({variable,documented:dict.some(d=>d.variable===variable)})));
console.log(`Wrote aggregate diagnostics to ${outDir}; rows=${rows.length}; linked=${linkedRows.length}; no participant-level rows emitted.`);
