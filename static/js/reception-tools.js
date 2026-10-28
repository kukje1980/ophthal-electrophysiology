/* Reception-desk helpers: reading what was typed into the search box, birth
   dates typed the Korean way (680302 = national-id front half), ages and
   "how long ago" labels. Pure functions, so they also load under node. */
(function (root) {
  "use strict";

  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const pad = (n) => String(n).padStart(2, "0");

  /* Local calendar date as YYYY-MM-DD (not UTC, so "today" is the PC's day). */
  function localISODate(d = new Date()) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  /* "19680302", "680302", "1968-03-02", "1968.3.2", "1968/03/02" -> "1968-03-02";
     6 digits read as YYMMDD (a year above this year's two digits is 19xx). */
  function parseBirth(s, today = new Date()) {
    s = String(s || "").trim();
    let y, m, d, g;
    if ((g = /^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$/.exec(s))) [y, m, d] = [+g[1], +g[2], +g[3]];
    else if (/^\d{8}$/.test(s)) [y, m, d] = [+s.slice(0, 4), +s.slice(4, 6), +s.slice(6)];
    else if (/^\d{6}$/.test(s)) {
      const yy = +s.slice(0, 2);
      y = yy <= today.getFullYear() % 100 ? 2000 + yy : 1900 + yy;
      [m, d] = [+s.slice(2, 4), +s.slice(4)];
    } else return null;
    const dt = new Date(y, m - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) return null;
    if (dt > today) return null;
    return `${y}-${pad(m)}-${pad(d)}`;
  }

  function ageOn(iso, today = new Date()) {
    if (!iso) return null;
    const [y, m, d] = iso.split("-").map(Number);
    let a = today.getFullYear() - y;
    if (today.getMonth() + 1 < m || (today.getMonth() + 1 === m && today.getDate() < d)) a--;
    return a;
  }

  /* Which registration field a search text belongs in when no patient
     matched: letters -> name, a separated date -> birth date, digits -> ID. */
  function classifyQuery(q) {
    q = String(q || "").trim();
    if (!q) return {};
    if (/[A-Za-z가-힣ㄱ-ㅎ]/.test(q)) return { name: q };
    if (/[-./]/.test(q) && parseBirth(q)) return { birth: q };
    return { mrn: q };
  }

  /* Escaped text with the matching prefix wrapped in <mark>. */
  function highlight(text, q) {
    text = String(text == null ? "" : text); q = String(q || "").trim();
    if (q && text.startsWith(q))
      return `<mark>${esc(text.slice(0, q.length))}</mark>${esc(text.slice(q.length))}`;
    return esc(text);
  }

  /* Sex from a key: 1/3 (male) and 2/4 (female) follow the national id. */
  function sexFromKey(k) {
    k = String(k || "").toLowerCase();
    if (["1", "3", "m", "남"].includes(k)) return "M";
    if (["2", "4", "f", "여"].includes(k)) return "F";
    return null;
  }

  /* "오늘" / "어제" / "5일 전" / "3개월 전" / "2년 전" for a past YYYY-MM-DD. */
  function sinceLabel(iso, today = new Date()) {
    if (!iso) return "";
    const [y, m, d] = iso.split("-").map(Number);
    const days = Math.round((new Date(today.getFullYear(), today.getMonth(), today.getDate())
                             - new Date(y, m - 1, d)) / 86400000);
    if (days <= 0) return "오늘";
    if (days === 1) return "어제";
    if (days < 31) return `${days}일 전`;
    if (days < 365) return `${Math.floor(days / 30.44)}개월 전`;
    return `${Math.floor(days / 365.25)}년 전`;
  }

  const SEX = { M: "남", F: "여", O: "기타" };
  const sexAge = (p) => [SEX[p.sex], p.age != null ? `${p.age}세` : null].filter(Boolean).join(" · ");

  const api = { esc, localISODate, parseBirth, ageOn, classifyQuery, highlight,
                sexFromKey, sinceLabel, sexAge };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ReceptionTools = api;
})(this);
