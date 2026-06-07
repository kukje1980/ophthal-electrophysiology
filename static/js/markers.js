/* Marker table rendering and flag styling. */

function flagClass(flag) {
  if (flag === "abnormal") return "flag-abn";
  if (flag === "borderline") return "flag-bord";
  return "flag-norm";
}

function markerTable(traces) {
  const rows = [];
  for (const tr of traces) {
    for (const m of tr.measurements || []) {
      rows.push(`
        <tr>
          <td>${tr.label}</td>
          <td><b>${m.marker}</b></td>
          <td>${m.latency_ms.toFixed(1)} ms</td>
          <td>${m.amplitude_uv.toFixed(2)} µV</td>
          <td><span class="badge ${flagClass(m.flag)}">${m.flag || "-"}</span></td>
        </tr>`);
    }
  }
  if (!rows.length) return `<p class="muted">No markers detected.</p>`;
  return `
    <table class="table compact">
      <thead><tr>
        <th>Eye</th><th>Marker</th><th>Implicit time</th>
        <th>Amplitude</th><th>Status</th>
      </tr></thead>
      <tbody>${rows.join("")}</tbody>
    </table>`;
}
