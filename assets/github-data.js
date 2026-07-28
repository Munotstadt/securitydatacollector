/* github-data.js
 * Gemeinsame Helper für alle HTML-Seiten des securitydatacollector Repos.
 * - Liest CSV-Dateien öffentlich via raw.githubusercontent.com (schnell, kein Token nötig)
 * - Schreibt CSV-Dateien via GitHub Contents API (Token nötig, "repo" Scope)
 * - Retry-on-409: falls die Datei zwischenzeitlich von einem Collector-Workflow
 *   verändert wurde (neuer SHA), wird die Datei neu geholt und der Schreibvorgang
 *   einmal wiederholt.
 *
 * Konfiguration (in localStorage, pro Browser):
 *   gh_owner   -> GitHub Benutzer-/Org-Name
 *   gh_repo    -> Repo-Name (z.B. "securitydatacollector")
 *   gh_branch  -> Branch (default "main")
 *   gh_token   -> Personal Access Token (nur nötig zum Schreiben/Speichern)
 */

const GH = {
  owner: localStorage.getItem('gh_owner') || '',
  repo: localStorage.getItem('gh_repo') || 'securitydatacollector',
  branch: localStorage.getItem('gh_branch') || 'main',
  token: localStorage.getItem('gh_token') || '',
};

function ghSaveConfig({ owner, repo, branch, token }) {
  if (owner !== undefined) { GH.owner = owner; localStorage.setItem('gh_owner', owner); }
  if (repo !== undefined) { GH.repo = repo; localStorage.setItem('gh_repo', repo); }
  if (branch !== undefined) { GH.branch = branch; localStorage.setItem('gh_branch', branch); }
  if (token !== undefined) { GH.token = token; localStorage.setItem('gh_token', token); }
}

function ghConfigured() {
  return !!(GH.owner && GH.repo);
}

/* Schnelles, öffentliches Lesen (kein Token, kein Rate-Limit-Problem, aber
 * bis zu ~60s CDN-Cache -> für Dashboard/Board ok, für Editor nutzen wir
 * stattdessen die Contents-API mit cache:no-store, damit der SHA aktuell ist. */
async function ghFetchRaw(path) {
  const url = `https://raw.githubusercontent.com/${GH.owner}/${GH.repo}/${GH.branch}/${path}`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Konnte ${path} nicht laden (${res.status})`);
  return res.text();
}

/* Holt Datei + SHA über die Contents API (nötig als Basis für ein Update). */
async function ghGetFile(path) {
  const url = `https://api.github.com/repos/${GH.owner}/${GH.repo}/contents/${encodeURIComponent(path)}?ref=${GH.branch}`;
  const headers = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
  if (GH.token) headers.Authorization = `Bearer ${GH.token}`;
  const res = await fetch(url, { headers, cache: 'no-store' });
  if (!res.ok) throw new Error(`GitHub Contents API Fehler (${res.status}) für ${path}`);
  const json = await res.json();
  const content = decodeURIComponent(escape(atob(json.content.replace(/\n/g, ''))));
  return { content, sha: json.sha };
}

/* Schreibt eine Datei zurück (Commit). Macht bei 409 (SHA veraltet) genau
 * einen erneuten Versuch mit frisch geholtem SHA. */
async function ghPutFile(path, newContent, message, sha) {
  if (!GH.token) throw new Error('Kein GitHub Token gesetzt - bitte in den Einstellungen hinterlegen.');
  const url = `https://api.github.com/repos/${GH.owner}/${GH.repo}/contents/${encodeURIComponent(path)}`;
  const body = {
    message,
    branch: GH.branch,
    sha,
    content: btoa(unescape(encodeURIComponent(newContent))),
  };
  const headers = {
    Authorization: `Bearer ${GH.token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  };
  let res = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(body) });
  if (res.status === 409) {
    // Datei wurde zwischenzeitlich geändert (z.B. durch einen Collector-Run) -> neu holen und einmal retryen
    const fresh = await ghGetFile(path);
    body.sha = fresh.sha;
    res = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(body) });
  }
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Speichern fehlgeschlagen (${res.status}): ${t}`);
  }
  return res.json();
}

/* ---- Minimaler CSV Parser/Writer (keine externen Libraries nötig) ---- */

function parseCSV(text) {
  const lines = text.replace(/\r\n/g, '\n').split('\n').filter(l => l.length > 0);
  if (lines.length === 0) return { header: [], rows: [] };
  const splitLine = (line) => {
    // Einfache CSV-Zellen, unterstützt Anführungszeichen für Kommas im Feld
    const cells = [];
    let cur = '', inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (inQuotes) {
        if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
        else if (c === '"') { inQuotes = false; }
        else { cur += c; }
      } else {
        if (c === '"') inQuotes = true;
        else if (c === ',') { cells.push(cur); cur = ''; }
        else cur += c;
      }
    }
    cells.push(cur);
    return cells;
  };
  const header = splitLine(lines[0]);
  const rows = lines.slice(1).map(l => {
    const cells = splitLine(l);
    const obj = {};
    header.forEach((h, i) => { obj[h] = cells[i] !== undefined ? cells[i] : ''; });
    return obj;
  });
  return { header, rows };
}

function toCSV(header, rows) {
  const escapeCell = (v) => {
    v = (v === undefined || v === null) ? '' : String(v);
    if (v.includes(',') || v.includes('"') || v.includes('\n')) {
      return '"' + v.replace(/"/g, '""') + '"';
    }
    return v;
  };
  const lines = [header.join(',')];
  for (const row of rows) {
    lines.push(header.map(h => escapeCell(row[h])).join(','));
  }
  return lines.join('\n') + '\n';
}

/* Zeitstempel im Format dd.mm.yyyy hh:mm:ss, Zeitzone Europe/Zurich (CET/CEST) */
function nowZurichString() {
  const parts = new Intl.DateTimeFormat('de-CH', {
    timeZone: 'Europe/Zurich',
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(new Date());
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
  return `${p.day}.${p.month}.${p.year} ${p.hour}:${p.minute}:${p.second}`;
}

/* Parst "dd.mm.yyyy hh:mm:ss" (angenommen Europe/Zurich lokal) zu einem JS Date-Objekt
 * für Berechnungen (Sortierung, Deltas). Nicht zeitzonenscharf, aber für
 * Anzeige/Delta-Zwecke ausreichend. */
function parseSwissDateTime(s) {
  if (!s) return null;
  const m = s.match(/(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})/);
  if (!m) return null;
  const [, d, mo, y, h, mi, se] = m;
  return new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(se));
}

/* Reines Datum "dd.mm.yyyy" (ohne Zeit) -> Date, z.B. für ExDate/PayDate. */
function parseSwissDate(s) {
  if (!s) return null;
  const m = s.match(/(\d{2})\.(\d{2})\.(\d{4})/);
  if (!m) return null;
  const [, d, mo, y] = m;
  return new Date(Number(y), Number(mo) - 1, Number(d));
}

/* Aktuelles Datum (Europe/Zurich) als "dd.mm.yyyy" (ohne Zeit). */
function nowZurichDateString() {
  const parts = new Intl.DateTimeFormat('de-CH', {
    timeZone: 'Europe/Zurich',
    day: '2-digit', month: '2-digit', year: 'numeric',
  }).formatToParts(new Date());
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
  return `${p.day}.${p.month}.${p.year}`;
}

/* Zahl mit fester Dezimalstellenzahl, de-CH Format (Punkt als Tausendertrenner-Vermeidung egal hier). */
function fmtDecimal(n, decimals) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return n.toLocaleString('de-CH', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/* Zeitstempel als "dd.mm. HH:MM" (fix, unabhängig von Locale-Eigenheiten). */
function fmtShortDateTime(date) {
  const dd = String(date.getDate()).padStart(2, '0');
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const hh = String(date.getHours()).padStart(2, '0');
  const mi = String(date.getMinutes()).padStart(2, '0');
  return `${dd}.${mm}. ${hh}:${mi}`;
}

/* Reines Datum "dd.mm.yyyy" für Anzeige. */
function fmtDateOnly(date) {
  const dd = String(date.getDate()).padStart(2, '0');
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}.${date.getFullYear()}`;
}

/* Findet in einer aufsteigend sortierten Liste { dt, ... } den letzten Eintrag
 * mit dt <= date. Wird für Vortag/Woche/Monat/YTD-Referenzwerte gebraucht. */
function findOnOrBefore(sortedAsc, date) {
  let best = null;
  for (const r of sortedAsc) {
    if (r.dt <= date && (!best || r.dt > best.dt)) best = r;
  }
  return best;
}

function daysAgo(fromDate, n) {
  const d = new Date(fromDate);
  d.setDate(d.getDate() - n);
  return d;
}

/* Baut { CCY: [ {dt, Price}, ... ] (aufsteigend sortiert) } aus Securities,
 * deren Name dem Muster "XXX/CHF" entspricht (z.B. "USD/CHF", "EUR/CHF").
 * `bySecurity` ist eine Map SecurityID -> [ {dt, Price}, ... ]. Damit lässt
 * sich die CHF-Umrechnung mit den SELBST erfassten FX-Kursen machen statt
 * mit einer externen Live-API - inkl. korrektem historischem Kurs für
 * Vortag/Monat-Referenzen (nicht nur der aktuelle Live-Kurs). */
function buildFxMap(master, bySecurity) {
  const fxMap = {};
  for (const m of master) {
    const match = (m.SecurityName || '').trim().match(/^([A-Za-z]{3})\/CHF$/i);
    if (!match) continue;
    const ccy = match[1].toUpperCase();
    const series = (bySecurity[m.SecurityID] || []).slice().sort((a, b) => a.dt - b.dt);
    if (series.length) fxMap[ccy] = series;
  }
  return fxMap;
}

function fxRateOnDate(fxMap, currency, date) {
  if (!currency || currency.toUpperCase() === 'CHF') return 1;
  const series = fxMap[currency.toUpperCase()];
  if (!series) return null;
  const ref = findOnOrBefore(series, date);
  return ref ? ref.Price : null;
}

/* Wie fxRateOnDate, liefert aber zusätzlich an, ob eine Näherung nötig war:
 * wenn für das Referenzdatum keine FX-Notierung existiert (z.B. weil die
 * FX-Historie kürzer ist als die Aktien-Historie - etwa nach einem
 * historischen Preis-Import nur für Aktien, nicht für FX-Paare), wird die
 * ÄLTESTE verfügbare FX-Notierung als bestmögliche Näherung verwendet,
 * statt gar keinen Wert zu liefern. */
function fxRateOnDateWithFallback(fxMap, currency, date) {
  if (!currency || currency.toUpperCase() === 'CHF') return { rate: 1, approx: false };
  const series = fxMap[currency.toUpperCase()];
  if (!series || !series.length) return { rate: null, approx: false };
  const exact = findOnOrBefore(series, date);
  if (exact) return { rate: exact.Price, approx: false };
  return { rate: series[0].Price, approx: true };
}
