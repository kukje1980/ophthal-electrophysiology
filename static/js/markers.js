/* Marker table rendering and flag styling. */

function flagClass(flag) {
  if (flag === "abnormal") return "flag-abn";
  if (flag === "borderline") return "flag-bord";
  return "flag-norm";
}

/* ISCEV PERG 2024: report the N95:P50 amplitude ratio per eye, which helps
   identify selective / predominant N95 loss. Only shown when both are present. */
function n95p50Ratios(traces) {
  const out = [];
  for (const tr of traces) {
    const ms = tr.measurements || [];
    const p50 = ms.find((m) => m.marker === "P50");
    const n95 = ms.find((m) => m.marker === "N95");
    if (p50 && n95 && Math.abs(p50.amplitude_uv) > 0) {
      out.push(`${tr.label} <b>${(Math.abs(n95.amplitude_uv) /
        Math.abs(p50.amplitude_uv)).toFixed(2)}</b>`);
    }
  }
  return out;
}

function markerTable(traces) {
  const rows = [];
  for (const tr of traces) {
    for (const m of tr.measurements || []) {
      rows.push(`
        <tr>
          <td><span class="eye-chip ${tr.label === "OS" ? "os" : "od"}">${tr.label}</span></td>
          <td><b class="mono">${m.marker}</b></td>
          <td class="num">${m.latency_ms.toFixed(1)}</td>
          <td class="num">${m.amplitude_uv.toFixed(2)}</td>
          <td><span class="badge ${flagClass(m.flag)}">${m.flag || "-"}</span></td>
        </tr>`);
    }
  }
  if (!rows.length) return `<p class="muted">검출된 마커가 없습니다 (No markers detected).</p>`;
  const ratios = n95p50Ratios(traces);
  const ratioLine = ratios.length
    ? `<p class="ratio-line">N95:P50 amplitude ratio · ${ratios.join(" · ")}</p>`
    : "";
  return `
    <div class="table-wrap"><table class="table compact">
      <thead><tr>
        <th>Eye</th><th>Marker</th><th class="num">Implicit <span class="unit">(ms)</span></th>
        <th class="num">Amp <span class="unit">(µV)</span></th><th>Status</th>
      </tr></thead>
      <tbody>${rows.join("")}</tbody>
    </table></div>${ratioLine}`;
}
