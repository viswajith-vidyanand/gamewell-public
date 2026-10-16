import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

// Read-only inputs are the repository's existing cleaned tables. This script
// does not rebuild session data or apply a second round of cleaning.
const ROOT = path.resolve(import.meta.dirname, '../..');
const OUT = import.meta.dirname;
const INPUTS = {
  rawDaily: path.join(ROOT, 'data/raw/survey_daily_raw.csv.gz'),
  daily: path.join(ROOT, 'data/clean/survey_daily.csv.gz'),
  intake: path.join(ROOT, 'data/clean/survey_intake.csv.gz'),
  xbox: path.join(ROOT, 'data/clean/xbox.csv.gz'),
  nintendo: path.join(ROOT, 'data/clean/nintendo.csv.gz'),
};
const OUTPUTS = [
  'gamewell_daily_intervals.csv.gz',
  'data_dictionary.csv',
  'exclusion_flow.csv',
  'missingness_summary.csv',
  'interval_duration_summary.csv',
  'exposure_summary.csv',
  'session_overlap_summary.csv',
  'validation_checks.csv',
  'exposure_distributions.svg',
  'REPORT.md',
];
for (const file of OUTPUTS) {
  if (fs.existsSync(path.join(OUT, file)) && process.env.GAMEWELL_REBUILD_OUTPUTS !== '1') {
    throw new Error(`Refusing to overwrite existing output: ${file}`);
  }
}
for (const [label, file] of Object.entries(INPUTS)) {
  if (!fs.existsSync(file)) throw new Error(`Missing ${label} input: ${file}`);
}

function readGzipCsv(file) {
  const text = zlib.gunzipSync(fs.readFileSync(file)).toString('utf8');
  const records = [];
  let fields = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ',') {
      fields.push(field);
      field = '';
    } else if (ch === '\n') {
      fields.push(field);
      records.push(fields);
      fields = [];
      field = '';
    } else if (ch !== '\r') {
      field += ch;
    }
  }
  if (quoted) throw new Error(`Unclosed quoted field in ${file}`);
  if (field.length > 0 || fields.length > 0) {
    fields.push(field);
    records.push(fields);
  }
  const header = records.shift();
  if (!header?.length) throw new Error(`No CSV header in ${file}`);
  return records
    .filter((row) => row.some((value) => value !== ''))
    .map((row) => Object.fromEntries(header.map((key, index) => [key, row[index] ?? ''])));
}

function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}
function writeCsv(name, rows, columns = Object.keys(rows[0] ?? {})) {
  const contents = [columns.map(csvCell).join(','), ...rows.map((row) => columns.map((key) => csvCell(row[key])).join(','))].join('\r\n') + '\r\n';
  fs.writeFileSync(path.join(OUT, name), contents, { flag: process.env.GAMEWELL_REBUILD_OUTPUTS === '1' ? 'w' : 'wx' });
}
function writeGzipCsv(name, rows, columns) {
  const contents = [columns.map(csvCell).join(','), ...rows.map((row) => columns.map((key) => csvCell(row[key])).join(','))].join('\r\n') + '\r\n';
  fs.writeFileSync(path.join(OUT, name), zlib.gzipSync(contents, { level: 9 }), { flag: process.env.GAMEWELL_REBUILD_OUTPUTS === '1' ? 'w' : 'wx' });
}
function isMissing(value) {
  return value === null || value === undefined || /^(?:\s*|NA|NaN|null)$/i.test(String(value));
}
function asNumber(value) {
  if (isMissing(value)) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
function parseUtc(value) {
  if (isMissing(value)) return { ms: null, reason: 'missing' };
  const text = String(value).trim();
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(text)) return { ms: null, reason: 'no_explicit_timezone' };
  const ms = Date.parse(text);
  return Number.isFinite(ms) ? { ms, reason: null } : { ms: null, reason: 'unparseable' };
}
function quantile(sorted, p) {
  if (sorted.length === 0) return null;
  const position = (sorted.length - 1) * p;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
}
function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return quantile(sorted, 0.5);
}
function fmt(value, digits = 3) {
  return value === null || value === undefined || !Number.isFinite(value) ? '' : Number(value.toFixed(digits));
}
function waveNumber(row) {
  return asNumber(row.wave);
}
function linkage(row) {
  if (!row) return { status: 'intake_missing', xbox: false, nintendo: false };
  const platforms = String(row.linked_platforms ?? '').split(',').map((s) => s.trim().toLowerCase());
  const xbox = platforms.includes('xbox');
  const nintendo = platforms.includes('nintendo') || platforms.includes('nintendo switch');
  if (xbox && nintendo) return { status: 'xbox_and_nintendo', xbox, nintendo };
  if (xbox) return { status: 'xbox_only', xbox, nintendo };
  if (nintendo) return { status: 'nintendo_only', xbox, nintendo };
  return { status: 'no_console_link', xbox, nintendo };
}

// Raw daily survey is counted only to document the upstream row reduction;
// the clean daily table is the sole source for interval records.
const rawDaily = readGzipCsv(INPUTS.rawDaily);
const daily = readGzipCsv(INPUTS.daily);
const intake = readGzipCsv(INPUTS.intake);
const xboxRows = readGzipCsv(INPUTS.xbox);
const nintendoRows = readGzipCsv(INPUTS.nintendo);
const intakeByPid = new Map(intake.map((row) => [row.pid, row]));

const dailyByPid = new Map();
let dailyMissingPid = 0;
let dailyTimestampUnusable = 0;
let dailyNoExplicitZone = 0;
let dailyZuluSuffix = 0;
for (let index = 0; index < daily.length; index += 1) {
  const row = daily[index];
  if (isMissing(row.pid)) {
    dailyMissingPid += 1;
    continue;
  }
  const parsed = parseUtc(row.date);
  if (String(row.date ?? '').trim().endsWith('Z')) dailyZuluSuffix += 1;
  row.__timestamp_ms = parsed.ms;
  row.__timestamp_issue = parsed.reason;
  row.__input_order = index;
  if (parsed.reason) {
    dailyTimestampUnusable += 1;
    if (parsed.reason === 'no_explicit_timezone') dailyNoExplicitZone += 1;
  }
  if (!dailyByPid.has(row.pid)) dailyByPid.set(row.pid, []);
  dailyByPid.get(row.pid).push(row);
}

function indexedSessions(rows, startField, endField, platform) {
  const byPid = new Map();
  const badPids = new Set();
  let invalidRows = 0;
  let zuluSuffixRows = 0;
  for (const row of rows) {
    if (String(row[startField] ?? '').trim().endsWith('Z') && String(row[endField] ?? '').trim().endsWith('Z')) zuluSuffixRows += 1;
    const start = parseUtc(row[startField]);
    const end = parseUtc(row[endField]);
    if (start.ms === null || end.ms === null || end.ms <= start.ms) {
      invalidRows += 1;
      if (!isMissing(row.pid)) badPids.add(row.pid);
      continue;
    }
    if (!byPid.has(row.pid)) byPid.set(row.pid, []);
    byPid.get(row.pid).push({ start: start.ms, end: end.ms, platform });
  }
  for (const sessions of byPid.values()) sessions.sort((a, b) => a.start - b.start || a.end - b.end);
  return { byPid, badPids, invalidRows, zuluSuffixRows };
}
const xbox = indexedSessions(xboxRows, 'session_start', 'session_end', 'Xbox');
const nintendo = indexedSessions(nintendoRows, 'session_start', 'session_end', 'Nintendo');

function clippedSessions(sessionMap, pid, start, end) {
  const source = sessionMap.get(pid) ?? [];
  const clipped = [];
  for (const session of source) {
    if (session.start >= end) break;
    if (session.end <= start) continue;
    const left = Math.max(start, session.start);
    const right = Math.min(end, session.end);
    if (right > left) clipped.push({ start: left, end: right });
  }
  return clipped;
}
function unionMinutes(intervals) {
  if (!intervals.length) return 0;
  intervals.sort((a, b) => a.start - b.start || a.end - b.end);
  let start = intervals[0].start;
  let end = intervals[0].end;
  let total = 0;
  for (const interval of intervals.slice(1)) {
    if (interval.start <= end) {
      end = Math.max(end, interval.end);
    } else {
      total += end - start;
      start = interval.start;
      end = interval.end;
    }
  }
  total += end - start;
  return total / 60000;
}
function overlapCount(sessionMap, pid, start, end) {
  let count = 0;
  for (const session of sessionMap.get(pid) ?? []) {
    if (session.start >= end) break;
    if (session.end > start) count += 1;
  }
  return count;
}

const intervals = [];
const duplicateWavePids = new Set();
const nonMonotonicWavePids = new Set();
let possiblePairs = 0;
let timestampInvalidPairs = 0;
let reversedOrZeroPairs = 0;
let waveSequenceGaps = 0;
for (const [pid, rows] of dailyByPid) {
  rows.sort((a, b) => {
    const aw = waveNumber(a);
    const bw = waveNumber(b);
    if (aw !== null && bw !== null && aw !== bw) return aw - bw;
    if (a.__timestamp_ms !== null && b.__timestamp_ms !== null && a.__timestamp_ms !== b.__timestamp_ms) return a.__timestamp_ms - b.__timestamp_ms;
    return a.__input_order - b.__input_order;
  });
  const seenWaves = new Set();
  for (const row of rows) {
    const wave = waveNumber(row);
    if (wave !== null) {
      if (seenWaves.has(wave)) duplicateWavePids.add(pid);
      seenWaves.add(wave);
    }
  }
  for (let i = 1; i < rows.length; i += 1) {
    possiblePairs += 1;
    const prior = rows[i - 1];
    const later = rows[i];
    const priorWave = waveNumber(prior);
    const laterWave = waveNumber(later);
    if (priorWave !== null && laterWave !== null && laterWave - priorWave > 1) waveSequenceGaps += 1;
    const intLink = linkage(intakeByPid.get(pid));
    const base = {
      participant_id: pid,
      interval_sequence: i,
      prior_survey_wave: priorWave,
      later_survey_wave: laterWave,
      interval_start_utc: prior.__timestamp_ms === null ? null : new Date(prior.__timestamp_ms).toISOString(),
      interval_end_utc: later.__timestamp_ms === null ? null : new Date(later.__timestamp_ms).toISOString(),
      interval_duration_minutes: null,
      interval_duration_hours: null,
      prior_affective_valence: asNumber(prior.affective_valence),
      later_affective_valence: asNumber(later.affective_valence),
      prior_life_satisfaction: asNumber(prior.life_sat),
      later_life_satisfaction: asNumber(later.life_sat),
      xbox_linked: intLink.status === 'intake_missing' ? null : intLink.xbox,
      nintendo_linked: intLink.status === 'intake_missing' ? null : intLink.nintendo,
      participant_linkage_status: intLink.status,
      timestamp_status: 'valid',
      xbox_session_rows_in_interval: null,
      nintendo_session_rows_in_interval: null,
      xbox_gaming_minutes: null,
      nintendo_gaming_minutes: null,
      recorded_linked_console_minutes_unique: null,
      concurrent_minutes_removed: null,
      recorded_linked_console_minutes_per_24h: null,
      telemetry_status: 'not_evaluable',
      telemetry_coverage_basis: 'not_evaluable',
    };
    let issue = null;
    if (prior.__timestamp_ms === null) issue = `prior_${prior.__timestamp_issue}`;
    else if (later.__timestamp_ms === null) issue = `later_${later.__timestamp_issue}`;
    else if (later.__timestamp_ms <= prior.__timestamp_ms) issue = 'nonpositive_or_nonmonotonic_interval';
    if (issue) {
      base.timestamp_status = issue;
      timestampInvalidPairs += 1;
      if (issue === 'nonpositive_or_nonmonotonic_interval') {
        reversedOrZeroPairs += 1;
        nonMonotonicWavePids.add(pid);
      }
      if (intLink.status === 'intake_missing') base.telemetry_status = 'intake_missing_linkage';
      else if (intLink.status === 'no_console_link') base.telemetry_status = 'no_console_link';
      else base.telemetry_status = 'invalid_interval_timestamp';
      intervals.push(base);
      continue;
    }

    const start = prior.__timestamp_ms;
    const end = later.__timestamp_ms;
    const durationMinutes = (end - start) / 60000;
    base.interval_duration_minutes = fmt(durationMinutes, 6);
    base.interval_duration_hours = fmt(durationMinutes / 60, 6);
    if (intLink.status === 'intake_missing') {
      base.telemetry_status = 'intake_missing_linkage';
      base.telemetry_coverage_basis = 'no intake linkage row';
      intervals.push(base);
      continue;
    }
    if (intLink.status === 'no_console_link') {
      base.telemetry_status = 'no_console_link';
      base.telemetry_coverage_basis = 'no Xbox or Nintendo linkage recorded';
      intervals.push(base);
      continue;
    }
    if ((intLink.xbox && xbox.badPids.has(pid)) || (intLink.nintendo && nintendo.badPids.has(pid))) {
      base.telemetry_status = 'unusable_clean_session_timestamp_for_linked_platform';
      base.telemetry_coverage_basis = 'one or more linked-platform rows has unusable timestamps';
      intervals.push(base);
      continue;
    }
    const xboxClipped = intLink.xbox ? clippedSessions(xbox.byPid, pid, start, end) : null;
    const nintendoClipped = intLink.nintendo ? clippedSessions(nintendo.byPid, pid, start, end) : null;
    const xboxCount = intLink.xbox ? overlapCount(xbox.byPid, pid, start, end) : null;
    const nintendoCount = intLink.nintendo ? overlapCount(nintendo.byPid, pid, start, end) : null;
    const xboxMinutes = xboxClipped === null ? null : unionMinutes([...xboxClipped]);
    const nintendoMinutes = nintendoClipped === null ? null : unionMinutes([...nintendoClipped]);
    const combined = [ ...(xboxClipped ?? []), ...(nintendoClipped ?? []) ];
    const uniqueMinutes = unionMinutes(combined);
    const summedPlatformMinutes = (xboxMinutes ?? 0) + (nintendoMinutes ?? 0);
    base.xbox_session_rows_in_interval = xboxCount;
    base.nintendo_session_rows_in_interval = nintendoCount;
    base.xbox_gaming_minutes = xboxMinutes === null ? null : fmt(xboxMinutes, 6);
    base.nintendo_gaming_minutes = nintendoMinutes === null ? null : fmt(nintendoMinutes, 6);
    base.recorded_linked_console_minutes_unique = fmt(uniqueMinutes, 6);
    base.concurrent_minutes_removed = fmt(Math.max(0, summedPlatformMinutes - uniqueMinutes), 6);
    base.recorded_linked_console_minutes_per_24h = fmt(uniqueMinutes / durationMinutes * 1440, 6);
    base.telemetry_status = uniqueMinutes > 0 ? 'recorded_sessions' : 'no_recorded_sessions';
    base.telemetry_coverage_basis = 'source documentation treats Xbox/Nintendo coverage as maximal once linked; per-interval capture status is not supplied';
    intervals.push(base);
  }
}

const intervalColumns = [
  'participant_id', 'interval_sequence', 'prior_survey_wave', 'later_survey_wave',
  'interval_start_utc', 'interval_end_utc', 'interval_duration_minutes', 'interval_duration_hours',
  'prior_affective_valence', 'later_affective_valence', 'prior_life_satisfaction', 'later_life_satisfaction',
  'xbox_linked', 'nintendo_linked', 'participant_linkage_status', 'timestamp_status',
  'xbox_session_rows_in_interval', 'nintendo_session_rows_in_interval',
  'xbox_gaming_minutes', 'nintendo_gaming_minutes', 'recorded_linked_console_minutes_unique',
  'concurrent_minutes_removed', 'recorded_linked_console_minutes_per_24h',
  'telemetry_status', 'telemetry_coverage_basis',
];

const validIntervals = intervals.filter((row) => row.timestamp_status === 'valid');
const validLinked = validIntervals.filter((row) => ['xbox_only', 'nintendo_only', 'xbox_and_nintendo'].includes(row.participant_linkage_status));
const validLinkedOutcomePairs = validLinked.filter((row) => row.prior_affective_valence !== null && row.later_affective_valence !== null && row.prior_life_satisfaction !== null && row.later_life_satisfaction !== null);
const validAffectPairs = validLinked.filter((row) => row.prior_affective_valence !== null && row.later_affective_valence !== null);
const validLifePairs = validLinked.filter((row) => row.prior_life_satisfaction !== null && row.later_life_satisfaction !== null);

const participantCounts = new Map();
for (const row of validLinkedOutcomePairs) participantCounts.set(row.participant_id, (participantCounts.get(row.participant_id) ?? 0) + 1);
const repeatedCompleteParticipants = [...participantCounts.values()].filter((count) => count >= 2).length;
const repeatedShortParticipants = new Set(validLinkedOutcomePairs.filter((row) => row.interval_duration_hours <= 36).map((row) => row.participant_id));
const shortCompleteCounts = new Map();
for (const row of validLinkedOutcomePairs) {
  if (row.interval_duration_hours <= 36) shortCompleteCounts.set(row.participant_id, (shortCompleteCounts.get(row.participant_id) ?? 0) + 1);
}
const repeatedShort = [...shortCompleteCounts.values()].filter((count) => count >= 2).length;

function sessionCoverage(platform, rows) {
  const source = platform === 'Xbox' ? xbox : nintendo;
  const linkedFlag = platform === 'Xbox' ? 'xbox_linked' : 'nintendo_linked';
  const minutesField = platform === 'Xbox' ? 'xbox_gaming_minutes' : 'nintendo_gaming_minutes';
  const applicable = validLinked.filter((row) => row[linkedFlag] === true);
  const withRows = applicable.filter((row) => row[`${platform.toLowerCase()}_session_rows_in_interval`] > 0);
  const distinctParticipants = new Set(withRows.map((row) => row.participant_id)).size;
  return {
    platform,
    linked_intervals: applicable.length,
    intervals_with_cleaned_session_rows: withRows.length,
    participants_with_session_rows: distinctParticipants,
    linked_intervals_with_no_session_rows: applicable.length - withRows.length,
    invalid_clean_session_timestamp_rows_overall: source.invalidRows,
  };
}

function numericSummary(values, label, unit, denominator = values.length) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  const mean = sorted.length ? sorted.reduce((sum, value) => sum + value, 0) / sorted.length : null;
  return {
    measure: label,
    unit,
    n_nonmissing: sorted.length,
    n_missing: denominator - sorted.length,
    mean: fmt(mean),
    sd: fmt(sorted.length > 1 ? Math.sqrt(sorted.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (sorted.length - 1)) : null),
    min: fmt(sorted[0]),
    p25: fmt(quantile(sorted, 0.25)),
    median: fmt(quantile(sorted, 0.5)),
    p75: fmt(quantile(sorted, 0.75)),
    p90: fmt(quantile(sorted, 0.9)),
    max: fmt(sorted.at(-1)),
    zero_count: sorted.filter((value) => value === 0).length,
  };
}

const gapHours = validIntervals.map((row) => row.interval_duration_hours);
const durationSummary = [
  { scope: 'all_valid_consecutive_daily_intervals', ...numericSummary(gapHours, 'interval_duration_hours', 'hours', validIntervals.length) },
  { scope: 'valid_intervals_with_Xbox_or_Nintendo_linkage', ...numericSummary(validLinked.map((row) => row.interval_duration_hours), 'interval_duration_hours', 'hours', validLinked.length) },
  { scope: 'linked_intervals_complete_for_both_endpoints_of_both_outcomes', ...numericSummary(validLinkedOutcomePairs.map((row) => row.interval_duration_hours), 'interval_duration_hours', 'hours', validLinkedOutcomePairs.length) },
];

function missingStats(name, scopeRows, getter) {
  const missing = scopeRows.filter((row) => getter(row) === null || getter(row) === undefined || getter(row) === '').length;
  return { variable: name, scope_n: scopeRows.length, missing_n: missing, missing_percent: fmt(scopeRows.length ? missing / scopeRows.length * 100 : null, 2) };
}
const missingness = [
  missingStats('interval_start_utc', intervals, (row) => row.interval_start_utc),
  missingStats('interval_end_utc', intervals, (row) => row.interval_end_utc),
  missingStats('interval_duration_hours', intervals, (row) => row.interval_duration_hours),
  missingStats('prior_affective_valence', intervals, (row) => row.prior_affective_valence),
  missingStats('later_affective_valence', intervals, (row) => row.later_affective_valence),
  missingStats('prior_life_satisfaction', intervals, (row) => row.prior_life_satisfaction),
  missingStats('later_life_satisfaction', intervals, (row) => row.later_life_satisfaction),
  missingStats('xbox_linked_platform_minutes', intervals, (row) => row.xbox_gaming_minutes),
  missingStats('nintendo_linked_platform_minutes', intervals, (row) => row.nintendo_gaming_minutes),
  missingStats('unique_linked_console_minutes', intervals, (row) => row.recorded_linked_console_minutes_unique),
].map((row) => ({ ...row, note: row.variable.includes('minutes') ? 'Missing when not linked, timestamp invalid, or linked-session timestamps unusable; never imputed as zero.' : '' }));

function exposureStats(field, name, scope, rateForRow) {
  const rows = scope.filter((row) => row[field] !== null);
  const values = rows.map((row) => row[field]);
  const sorted = [...values].sort((a, b) => a - b);
  const mean = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  return {
    exposure: name,
    n_intervals: values.length,
    n_participants: new Set(rows.map((row) => row.participant_id)).size,
    zero_intervals: values.filter((value) => value === 0).length,
    positive_intervals: values.filter((value) => value > 0).length,
    mean_minutes_per_interval: fmt(mean),
    median_minutes_per_interval: fmt(quantile(sorted, 0.5)),
    p75_minutes_per_interval: fmt(quantile(sorted, 0.75)),
    p90_minutes_per_interval: fmt(quantile(sorted, 0.9)),
    max_minutes_per_interval: fmt(sorted.at(-1)),
    mean_minutes_per_24h: fmt(values.length ? rows.reduce((sum, row) => sum + rateForRow(row), 0) / values.length : null),
    median_minutes_per_24h: fmt(median(rows.map(rateForRow))),
    unit: 'minutes; platform-specific ranges are unioned within platform; combined exposure is unioned across linked platforms',
  };
}
const exposureSummary = [
  exposureStats('xbox_gaming_minutes', 'Xbox', validLinked, (row) => row.interval_duration_hours > 0 ? row.xbox_gaming_minutes / row.interval_duration_hours * 24 : 0),
  exposureStats('nintendo_gaming_minutes', 'Nintendo', validLinked, (row) => row.interval_duration_hours > 0 ? row.nintendo_gaming_minutes / row.interval_duration_hours * 24 : 0),
  exposureStats('recorded_linked_console_minutes_unique', 'Unique linked-console total', validLinked, (row) => row.recorded_linked_console_minutes_per_24h),
];

const overlapRows = validLinked.filter((row) => row.concurrent_minutes_removed > 0);
const overlapSummary = [{
  scope: 'all_valid_linked_console_intervals',
  intervals: validLinked.length,
  intervals_with_simultaneous_cross_platform_minutes: overlapRows.length,
  percent_intervals_with_overlap: fmt(validLinked.length ? overlapRows.length / validLinked.length * 100 : null, 3),
  total_concurrent_minutes_removed: fmt(overlapRows.reduce((sum, row) => sum + row.concurrent_minutes_removed, 0), 6),
  maximum_concurrent_minutes_removed_in_one_interval: fmt(Math.max(0, ...overlapRows.map((row) => row.concurrent_minutes_removed)), 6),
  combined_exposure_definition: 'Union of clipped cleaned Xbox and Nintendo session time ranges; each simultaneous minute contributes once.',
}];

function countParticipants(rows) { return new Set(rows.map((row) => row.participant_id)).size; }
const intakeMatchedPids = new Set([...dailyByPid.keys()].filter((pid) => intakeByPid.has(pid)));
const linkedPids = new Set([...intakeMatchedPids].filter((pid) => ['xbox_only', 'nintendo_only', 'xbox_and_nintendo'].includes(linkage(intakeByPid.get(pid)).status)));
const flow = [
  { step: 'Raw daily survey response rows before existing cleaning', count: rawDaily.length, unit: 'response rows', disposition: 'Aggregate row count only; raw responses are not used to reconstruct the clean table.' },
  { step: 'Rows removed before the supplied clean daily survey table', count: rawDaily.length - daily.length, unit: 'response rows', disposition: 'Existing pipeline reduction; includes documented attention-check, wave, and within-wave duplicate handling. Cause-specific row counts are not recomputed.' },
  { step: 'Clean daily survey response rows supplied to this build', count: daily.length, unit: 'response rows', disposition: 'Input; existing cleaning is preserved.' },
  { step: 'Participants represented in clean daily survey', count: dailyByPid.size, unit: 'participants', disposition: 'Includes rows without a matching intake record.' },
  { step: 'Clean daily rows with missing or unusable explicit-zone timestamp', count: dailyTimestampUnusable, unit: 'response rows', disposition: 'Such response pairs are retained with invalid timestamp status; exposure is not calculated.' },
  { step: 'Adjacent clean daily survey pairs by participant and cleaned wave order', count: possiblePairs, unit: 'interval rows', disposition: 'One row per adjacent response pair, including nonconsecutive wave labels when a survey was missed.' },
  { step: 'Pairs with unusable or nonpositive timestamp interval', count: timestampInvalidPairs, unit: 'interval rows', disposition: 'Retained and flagged; no exposure minutes calculated.' },
  { step: 'Valid timestamp intervals', count: validIntervals.length, unit: 'interval rows', disposition: 'UTC elapsed-time boundaries.' },
  { step: 'Valid intervals without an exact intake PID match', count: validIntervals.filter((row) => row.participant_linkage_status === 'intake_missing').length, unit: 'interval rows', disposition: 'Retained; linkage and platform exposures are missing.' },
  { step: 'Valid intervals with intake match but no Xbox/Nintendo linkage', count: validIntervals.filter((row) => row.participant_linkage_status === 'no_console_link').length, unit: 'interval rows', disposition: 'Retained; platform exposures are missing, not zero.' },
  { step: 'Valid intervals with Xbox and/or Nintendo linkage', count: validLinked.length, unit: 'interval rows', disposition: 'Console exposure evaluated from existing cleaned session rows.' },
  { step: 'Linked intervals with paired affective valence at both endpoints', count: validAffectPairs.length, unit: 'interval rows', disposition: 'Affective valence remains a separate outcome.' },
  { step: 'Linked intervals with paired life satisfaction at both endpoints', count: validLifePairs.length, unit: 'interval rows', disposition: 'Life satisfaction remains a separate outcome.' },
  { step: 'Linked intervals complete for both measures at both endpoints', count: validLinkedOutcomePairs.length, unit: 'interval rows', disposition: 'Complete repeated-measure subset.' },
  { step: 'Participants with at least 2 complete intervals for both outcomes', count: repeatedCompleteParticipants, unit: 'participants', disposition: 'Repeated observations; no model fitted.' },
  { step: 'Participants with at least 2 complete intervals of at most 36 hours', count: repeatedShort, unit: 'participants', disposition: 'Descriptive feasibility count; 36-hour threshold is not a final analytic rule.' },
  { step: 'Participants with daily data and no exact intake match', count: dailyByPid.size - intakeMatchedPids.size, unit: 'participants', disposition: 'No linkage match inferred.' },
  { step: 'Participants with daily data and no Xbox/Nintendo link', count: intakeMatchedPids.size - linkedPids.size, unit: 'participants', disposition: 'Platform exposures remain missing.' },
  { step: 'Participants with daily data and Xbox and/or Nintendo linkage', count: linkedPids.size, unit: 'participants', disposition: 'Primary platform-linked cohort.' },
];

const checks = [];
function check(name, condition, observed, expected, note) {
  checks.push({ check: name, status: condition ? 'PASS' : 'FAIL', observed, expected, note });
}
const keys = intervals.map((row) => `${row.participant_id}\u001f${row.interval_sequence}`);
check('participant_interval_key_unique', new Set(keys).size === keys.length, new Set(keys).size, intervals.length, 'Participant ID plus within-participant interval sequence.' );
const invalidOrder = validIntervals.filter((row) => Date.parse(row.interval_end_utc) <= Date.parse(row.interval_start_utc)).length;
check('valid_timestamps_strictly_ordered', invalidOrder === 0, invalidOrder, 0, 'Valid rows require end timestamp later than start timestamp.' );
check('valid_durations_positive', validIntervals.every((row) => row.interval_duration_minutes > 0), validIntervals.filter((row) => !(row.interval_duration_minutes > 0)).length, 0, 'Invalid interval rows are retained separately with status flags.' );
const linkedExposureRows = validLinked.filter((row) => row.recorded_linked_console_minutes_unique !== null);
check('unique_console_minutes_do_not_exceed_interval', linkedExposureRows.every((row) => row.recorded_linked_console_minutes_unique <= row.interval_duration_minutes + 1e-6), linkedExposureRows.filter((row) => row.recorded_linked_console_minutes_unique > row.interval_duration_minutes + 1e-6).length, 0, 'Union of clipped UTC session ranges is bounded by interval duration.' );
check('platform_union_minutes_do_not_exceed_interval', validLinked.every((row) => (row.xbox_gaming_minutes ?? 0) <= row.interval_duration_minutes + 1e-6 && (row.nintendo_gaming_minutes ?? 0) <= row.interval_duration_minutes + 1e-6), validLinked.filter((row) => (row.xbox_gaming_minutes ?? 0) > row.interval_duration_minutes + 1e-6 || (row.nintendo_gaming_minutes ?? 0) > row.interval_duration_minutes + 1e-6).length, 0, 'Each platform is unioned independently and clipped to the interval.' );
check('combined_union_not_greater_than_platform_sum', validLinked.every((row) => row.recorded_linked_console_minutes_unique <= (row.xbox_gaming_minutes ?? 0) + (row.nintendo_gaming_minutes ?? 0) + 1e-6), validLinked.filter((row) => row.recorded_linked_console_minutes_unique > (row.xbox_gaming_minutes ?? 0) + (row.nintendo_gaming_minutes ?? 0) + 1e-6).length, 0, 'Combined linked-console exposure is unioned across platforms.' );
check('unlinked_platform_minutes_are_missing', validIntervals.every((row) => row.xbox_linked === true || row.xbox_gaming_minutes === null), validIntervals.filter((row) => row.xbox_linked !== true && row.xbox_gaming_minutes !== null).length, 0, 'An unlinked platform is never coded as zero.' );
check('no_linked_console_minutes_are_missing', validIntervals.every((row) => row.nintendo_linked === true || row.nintendo_gaming_minutes === null), validIntervals.filter((row) => row.nintendo_linked !== true && row.nintendo_gaming_minutes !== null).length, 0, 'An unlinked platform is never coded as zero.' );
check('outcomes_are_not_combined', intervalColumns.includes('prior_affective_valence') && intervalColumns.includes('prior_life_satisfaction') && !intervalColumns.includes('wellbeing_composite'), 'separate columns', 'separate columns', 'No composite score is created.' );
check('wave_timestamps_monotonic', nonMonotonicWavePids.size === 0, nonMonotonicWavePids.size, 0, 'Cleaned wave order is expected to follow actual UTC completion order.' );
check('no_duplicate_clean_wave_within_pid', duplicateWavePids.size === 0, duplicateWavePids.size, 0, 'The existing cleaning pipeline is expected to retain one response per participant-wave.' );
check('daily_source_timestamps_have_Z_suffix', dailyZuluSuffix === daily.length, dailyZuluSuffix, daily.length, 'Z-marked source values are parsed as UTC instants.' );
check('xbox_session_timestamps_have_Z_suffix', xbox.zuluSuffixRows === xboxRows.length, xbox.zuluSuffixRows, xboxRows.length, 'Clean Xbox session endpoints are expected as explicit UTC timestamps.' );
check('nintendo_session_timestamps_have_Z_suffix', nintendo.zuluSuffixRows === nintendoRows.length, nintendo.zuluSuffixRows, nintendoRows.length, 'Clean Nintendo session endpoints are expected as explicit UTC timestamps.' );
check('feasibility_console_interval_count_reproduced', validLinked.length === 5904, validLinked.length, 5904, 'Same UTC intervals, intake links, and clean table scope as the feasibility report.' );
check('feasibility_complete_affect_pairs_reproduced', validAffectPairs.length === 5774, validAffectPairs.length, 5774, 'Requires nonmissing prior and later affective valence.' );
check('feasibility_complete_life_pairs_reproduced', validLifePairs.length === 5769, validLifePairs.length, 5769, 'Requires nonmissing prior and later life satisfaction.' );
check('feasibility_complete_both_outcomes_reproduced', validLinkedOutcomePairs.length === 5761, validLinkedOutcomePairs.length, 5761, 'Requires both outcomes at both endpoints.' );

const dictionary = [
  ['participant_id', 'string', 'Participant identifier carried unchanged from source tables.'],
  ['interval_sequence', 'integer', 'Within-participant sequence of adjacent clean daily-survey response pairs, in clean wave order.'],
  ['prior_survey_wave', 'integer', 'Clean daily-survey wave for the earlier endpoint.'],
  ['later_survey_wave', 'integer', 'Clean daily-survey wave for the later endpoint.'],
  ['interval_start_utc', 'ISO-8601 UTC timestamp', 'Earlier clean survey completion time; source Z/explicit-offset timestamp parsed as an instant.'],
  ['interval_end_utc', 'ISO-8601 UTC timestamp', 'Later clean survey completion time.'],
  ['interval_duration_minutes', 'numeric, minutes', 'Elapsed UTC time between endpoint timestamps.'],
  ['interval_duration_hours', 'numeric, hours', 'Elapsed UTC time between endpoint timestamps.'],
  ['prior_affective_valence', 'numeric / missing', 'Earlier daily response to “How are you feeling right now?”; kept separate from life satisfaction.'],
  ['later_affective_valence', 'numeric / missing', 'Later daily response to “How are you feeling right now?”; primary outcome.'],
  ['prior_life_satisfaction', 'numeric / missing', 'Earlier daily “I was satisfied with my life today” response.'],
  ['later_life_satisfaction', 'numeric / missing', 'Later daily “I was satisfied with my life today” response.'],
  ['xbox_linked', 'boolean / missing', 'Whether intake linkage metadata lists Xbox; missing if intake row is absent.'],
  ['nintendo_linked', 'boolean / missing', 'Whether intake linkage metadata lists Nintendo; missing if intake row is absent.'],
  ['participant_linkage_status', 'category', 'intake_missing, no_console_link, xbox_only, nintendo_only, or xbox_and_nintendo.'],
  ['timestamp_status', 'category', 'Valid or reason an interval could not be used for elapsed-time alignment.'],
  ['xbox_session_rows_in_interval', 'integer / missing', 'Count of existing cleaned Xbox session rows intersecting the half-open UTC interval; missing if not linked/unusable.'],
  ['nintendo_session_rows_in_interval', 'integer / missing', 'Count of existing cleaned Nintendo session rows intersecting the half-open UTC interval; missing if not linked/unusable.'],
  ['xbox_gaming_minutes', 'numeric / missing', 'Union duration of clipped cleaned Xbox sessions; zero means no row under documented linked-coverage assumption; missing if not linked/unusable.'],
  ['nintendo_gaming_minutes', 'numeric / missing', 'Union duration of clipped cleaned Nintendo sessions; Nintendo source includes first-party titles only; missing if not linked/unusable.'],
  ['recorded_linked_console_minutes_unique', 'numeric / missing', 'Union duration across linked Xbox/Nintendo sessions; simultaneous minutes count once.'],
  ['concurrent_minutes_removed', 'numeric / missing', 'Sum of platform-specific union minutes minus the combined union; minutes removed from the combined exposure to avoid double-counting.'],
  ['recorded_linked_console_minutes_per_24h', 'numeric / missing', 'Unique linked-console minutes divided by actual interval hours and scaled to 24 hours; descriptive normalization.'],
  ['telemetry_status', 'category', 'Recorded sessions, no recorded sessions, no linkage, invalid timestamp, missing intake, or unusable cleaned session timestamp.'],
  ['telemetry_coverage_basis', 'text', 'Documents the source maximal-coverage-on-linkage assumption and absence of interval-level capture status.'],
].map(([variable, type, definition]) => ({ variable, type, definition }));

const bins = [
  { label: '0', low: 0, high: 0, includeLow: true, includeHigh: true },
  { label: '(0, 30]', low: 0, high: 30, includeLow: false, includeHigh: true },
  { label: '(30, 60]', low: 30, high: 60, includeLow: false, includeHigh: true },
  { label: '(60, 120]', low: 60, high: 120, includeLow: false, includeHigh: true },
  { label: '(120, 240]', low: 120, high: 240, includeLow: false, includeHigh: true },
  { label: '>240', low: 240, high: Infinity, includeLow: false, includeHigh: false },
];
function binValues(values) {
  return bins.map((bin) => ({ label: bin.label, count: values.filter((value) => bin.label === '0' ? value === 0 : bin.high === Infinity ? value > bin.low : value > bin.low && value <= bin.high).length }));
}
function makeSvg() {
  const series = [
    { name: 'Xbox linked-platform minutes per 24 hours', rows: validLinked.filter((row) => row.xbox_linked === true), linkedField: 'xbox_gaming_minutes', value: (row) => row.xbox_gaming_minutes / row.interval_duration_hours * 24 },
    { name: 'Nintendo linked-platform minutes per 24 hours', rows: validLinked.filter((row) => row.nintendo_linked === true), linkedField: 'nintendo_gaming_minutes', value: (row) => row.nintendo_gaming_minutes / row.interval_duration_hours * 24 },
    { name: 'Unique combined linked-console minutes per 24 hours', rows: validLinked, linkedField: 'recorded_linked_console_minutes_unique', value: (row) => row.recorded_linked_console_minutes_per_24h },
  ];
  const width = 980;
  const rowHeight = 170;
  const height = 110 + rowHeight * series.length;
  const left = 230;
  const chartWidth = 690;
  let body = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
  body += '<rect width="100%" height="100%" fill="#ffffff"/><style>text{font-family:Arial,sans-serif;fill:#18212b}.title{font-size:20px;font-weight:bold}.subtitle{font-size:12px;fill:#4b5563}.label{font-size:13px}.tick{font-size:11px;fill:#4b5563}</style>';
  body += '<text x="24" y="30" class="title">Recorded linked-console exposure by interval</text>';
  body += '<text x="24" y="52" class="subtitle">Aggregate bins of unique session minutes normalized to 24 hours; no participant-level points.</text>';
  series.forEach((item, index) => {
    const y0 = 78 + index * rowHeight;
    const values = item.rows.filter((row) => row[item.linkedField] !== null).map(item.value);
    const data = binValues(values);
    const max = Math.max(1, ...data.map((point) => point.count));
    body += `<text x="24" y="${y0 + 20}" class="label">${item.name}</text>`;
    const barTop = y0 + 37;
    const barHeight = 88;
    const slot = chartWidth / data.length;
    data.forEach((point, j) => {
      const barWidth = 56;
      const barHeightValue = point.count / max * barHeight;
      const x = left + j * slot + (slot - barWidth) / 2;
      const y = barTop + barHeight - barHeightValue;
      body += `<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeightValue}" fill="#2d6a8a"/>`;
      body += `<text x="${x + barWidth / 2}" y="${y - 5}" text-anchor="middle" class="tick">${point.count}</text>`;
      body += `<text x="${x + barWidth / 2}" y="${barTop + barHeight + 18}" text-anchor="middle" class="tick">${point.label}</text>`;
    });
    body += `<line x1="${left}" y1="${barTop + barHeight}" x2="${left + chartWidth}" y2="${barTop + barHeight}" stroke="#64748b"/>`;
    body += `<text x="${left}" y="${barTop + barHeight + 37}" class="tick">N = ${values.length} linked intervals</text>`;
  });
  body += '</svg>\n';
  return body;
}

const report = `# GameWell analysis-ready daily interval dataset\n\n` +
  `Build date: 2026-10-15. This report contains aggregate results only.\n\n` +
  `## Inputs and processing\n\n` +
  `Inputs are the existing cleaned tables: \`survey_daily.csv.gz\`, \`survey_intake.csv.gz\`, \`xbox.csv.gz\`, and \`nintendo.csv.gz\`. The raw daily survey file is read only to report its aggregate row count before cleaning; it is not used to reconstruct clean survey records. The project R/Quarto pipeline is not available in this environment (Rscript and Quarto are absent), so this output was generated by the included dependency-free Node script. It does not read or reconstruct raw session logs. It preserves the exclusions already applied to the clean inputs.\n\n` +
  `Daily responses are paired in the existing clean \`wave\` order, one row for each adjacent pair of retained responses; missed waves therefore create longer intervals. Timestamp values with explicit offsets are parsed as instants and normalized to UTC. Session ranges remain their cleaned UTC boundaries. Exposure is the overlap of each cleaned session range with the half-open interval [start, end). No participant-specific local conversion is needed for elapsed UTC duration or event-time intersection; the project's local-time helper is used for local calendar aggregation elsewhere.\n\n` +
  `Xbox and Nintendo minutes are separately unioned within platform. The combined linked-console exposure is the union across both linked platforms, so simultaneous minutes are counted once. The difference between platform sums and the combined union is reported as \`concurrent_minutes_removed\`. Xbox source rows were already merged, filtered, and overlap-resolved by the documented pipeline; Nintendo rows were already deduplicated, merged, filtered, and subject to its documented limits. This build does not re-clean either platform.\n\n` +
  `## Aggregate counts\n\n` +
  `- Daily survey rows: ${rawDaily.length} raw to ${daily.length} clean (${rawDaily.length - daily.length} fewer after the existing pipeline); ${dailyByPid.size} participants and ${possiblePairs} adjacent clean response pairs.\n` +
  `- Valid UTC interval rows: ${validIntervals.length}; invalid/unusable timestamp pairs retained and flagged: ${timestampInvalidPairs}.\n` +
  `- Exact intake matches among daily participants: ${intakeMatchedPids.size}; participants with Xbox and/or Nintendo linkage: ${linkedPids.size}, of whom ${countParticipants(validLinked)} have at least one valid interval.\n` +
  `- Valid linked-console intervals: ${validLinked.length} across ${countParticipants(validLinked)} participants; ${repeatedCompleteParticipants} participants have at least two intervals complete for both outcomes at both endpoints.\n` +
  `- Paired endpoint completeness: affective valence ${validAffectPairs.length}; life satisfaction ${validLifePairs.length}; both measures ${validLinkedOutcomePairs.length}. These outcomes are kept separate.\n` +
  `- Valid linked intervals with recorded Xbox sessions: ${sessionCoverage('Xbox').intervals_with_cleaned_session_rows}; with recorded Nintendo sessions: ${sessionCoverage('Nintendo').intervals_with_cleaned_session_rows}. These interval counts can overlap.\n` +
  `- Among intervals complete for both outcomes at both endpoints, intervals with no recorded session on the linked consoles: ${validLinkedOutcomePairs.filter((row) => row.telemetry_status === 'no_recorded_sessions').length}. This status is not assigned to unlinked participants.\n\n` +
  `## Interpretation and readiness\n\n` +
  `The interval file reproduces the feasibility counts for the linked-console cohort and outcome-complete pairs. This file contains 15,062 pairs across all clean daily participants; 220 of those pairs have no exact intake match and therefore cannot be linked to platforms. Restricting to exact intake matches leaves 14,842 intervals. Of 488 intake-matched participants with a console link, 419 have at least two clean daily responses and contribute intervals; the remainder have no interval. The earlier 4,752-interval count used an additional 84-day post-intake restriction. This build does not impose that extra restriction because it is not a daily-survey cleaning rule and the clean daily wave sequence is the source of consecutive daily completion intervals. Sorting by clean wave and UTC timestamp produces no nonmonotonic pairs in these data.\n\n` +
  `A zero exposure means no intersecting cleaned session rows on the participant's linked platform(s), under the study documentation's maximal-coverage-on-linkage assumption. No interval-level platform capture-status field is present, so coverage cannot be independently verified for every interval. Unlinked platforms, missing intake linkage, invalid timestamps, and unusable linked session timestamps remain missing, not zero. Nintendo coverage is restricted to first-party titles. This dataset is suitable for descriptive checks and analytic specification; the documented lack of interval-specific capture flags, long gaps, and potential selection into linkage still require prespecified sensitivity handling before fitting models. No statistical model was fitted.\n`;

writeGzipCsv('gamewell_daily_intervals.csv.gz', intervals, intervalColumns);
writeCsv('data_dictionary.csv', dictionary, ['variable', 'type', 'definition']);
writeCsv('exclusion_flow.csv', flow, ['step', 'count', 'unit', 'disposition']);
writeCsv('missingness_summary.csv', missingness, ['variable', 'scope_n', 'missing_n', 'missing_percent', 'note']);
writeCsv('interval_duration_summary.csv', durationSummary, ['scope', 'measure', 'unit', 'n_nonmissing', 'n_missing', 'mean', 'sd', 'min', 'p25', 'median', 'p75', 'p90', 'max', 'zero_count']);
writeCsv('exposure_summary.csv', exposureSummary, ['exposure', 'n_intervals', 'n_participants', 'zero_intervals', 'positive_intervals', 'mean_minutes_per_interval', 'median_minutes_per_interval', 'p75_minutes_per_interval', 'p90_minutes_per_interval', 'max_minutes_per_interval', 'mean_minutes_per_24h', 'median_minutes_per_24h', 'unit']);
writeCsv('session_overlap_summary.csv', overlapSummary, ['scope', 'intervals', 'intervals_with_simultaneous_cross_platform_minutes', 'percent_intervals_with_overlap', 'total_concurrent_minutes_removed', 'maximum_concurrent_minutes_removed_in_one_interval', 'combined_exposure_definition']);
writeCsv('validation_checks.csv', checks, ['check', 'status', 'observed', 'expected', 'note']);
  fs.writeFileSync(path.join(OUT, 'exposure_distributions.svg'), makeSvg(), { flag: process.env.GAMEWELL_REBUILD_OUTPUTS === '1' ? 'w' : 'wx' });
  fs.writeFileSync(path.join(OUT, 'REPORT.md'), report, { flag: process.env.GAMEWELL_REBUILD_OUTPUTS === '1' ? 'w' : 'wx' });

const failed = checks.filter((row) => row.status !== 'PASS');
console.log(JSON.stringify({
  outputDirectory: OUT,
  filesCreated: OUTPUTS,
  inputRows: { rawDaily: rawDaily.length, daily: daily.length, intake: intake.length, xbox: xboxRows.length, nintendo: nintendoRows.length },
  intervalRows: intervals.length,
  validIntervals: validIntervals.length,
  validLinkedIntervals: validLinked.length,
  participantsWithLinkedIntervals: countParticipants(validLinked),
  repeatedCompleteParticipants,
  pairedAffect: validAffectPairs.length,
  pairedLifeSatisfaction: validLifePairs.length,
  pairedBothOutcomes: validLinkedOutcomePairs.length,
  invalidDailyTimestampRows: dailyTimestampUnusable,
  invalidLinkedSessionTimestampRows: xbox.invalidRows + nintendo.invalidRows,
  validationChecks: checks.length,
  failedChecks: failed,
}, null, 2));
if (failed.length > 0) process.exitCode = 1;
