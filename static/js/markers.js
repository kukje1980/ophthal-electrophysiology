/* Marker table rendering and flag styling. */

function flagClass(flag) {
  if (flag === "abnormal") return "flag-abn";
  if (flag === "borderline") return "flag-bord";
  return "flag-norm";
}

const FLAG_KO = { normal: "정상", borderline: "경계", abnormal: "비정상" };

/* ISCEV PERG 2024: report the N95:P50 amplitude ratio per eye, which helps
   identify selective / predominant N95 loss. Only shown when both are present. */
function n95p50Ratios(traces) {
  const out = [];
  for (const tr of traces) {
    const ms = tr.measurements || [];
    const p50 = ms.find((m) => m.marker === "P50");
    const n95 = ms.find((m) => m.marker === "N95");
    if (p50 && n95 && Math.abs(p50.amplitude_uv) > 0) {
      out.push(`${tr.label}: ${(Math.abs(n95.amplitude_uv) /
        Math.abs(p50.amplitude_uv)).toFixed(2)}`);
    }
  }
  return out;
}

/* One compact table per eye, side by side. */
function markerTable(traces) {
  const blocks = [];
  for (const tr of traces) {
    const ms = tr.measurements || [];
    const eyeCls = tr.label === "OS" ? "os" : "od";
    const rows = ms.map((m) => `
        <tr>
          <td class="mk">${m.marker}</td>
          <td class="num">${m.latency_ms.toFixed(1)}<span class="dim"> ms</span></td>
          <td class="num">${m.amplitude_uv.toFixed(2)}<span class="dim"> µV</span></td>
          <td><span class="badge ${flagClass(m.flag)}">${FLAG_KO[m.flag] || m.flag || "-"}</span></td>
        </tr>`).join("");
    blocks.push(`
      <div class="eye-tbl">
        <div class="eye-h"><i class="dot ${eyeCls}"></i><span class="eye ${eyeCls}">${tr.label}</span>
          <span class="muted">${tr.label === "OD" ? "우안" : tr.label === "OS" ? "좌안" : ""}</span>
          <span class="grow"></span><span class="muted">${ms.length} markers</span></div>
        ${rows ? `<table class="table compact">
          <thead><tr><th>Marker</th><th>Implicit time</th><th>Amplitude</th><th>판정</th></tr></thead>
          <tbody>${rows}</tbody></table>` : `<p class="empty">No markers detected.</p>`}
      </div>`);
  }
  if (!blocks.length) return `<p class="empty">No markers detected.</p>`;
  const ratios = n95p50Ratios(traces);
  const ratioLine = ratios.length
    ? `<p class="muted ratio-line">N95:P50 amplitude ratio — ${ratios.join(" · ")}</p>`
    : "";
  return `<div class="wf-markers">${blocks.join("")}</div>${ratioLine}`;
}
