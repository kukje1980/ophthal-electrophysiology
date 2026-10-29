/* Marker table rendering, flag styling, interocular comparison table. */

function flagClass(flag) {
  if (flag === "abnormal") return "flag-abn";
  if (flag === "borderline") return "flag-bord";
  return "flag-norm";
}

const FLAG_KO = { normal: "정상", borderline: "경계", abnormal: "비정상" };
function flagBadge(flag) {
  const f = flag || "normal";
  return `<span class="badge ${flagClass(f)}">${FLAG_KO[f] || f}</span>`;
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

/* Marker table. With opts.editable each row gets an editable implicit-time
   field and a delete button; each trace gets "add marker" + "auto re-detect".
   Interaction is wired up by renderExam (acquisition.js) through data-*
   attributes, so this stays pure markup. */
function markerTable(traces, opts = {}) {
  const editable = !!opts.editable;
  const rows = [];
  traces.forEach((tr, ti) => {
    const ms = (tr.measurements || []).slice().sort((a, b) => a.latency_ms - b.latency_ms);
    for (const m of ms) {
      const armed = opts.armed && opts.armed.traceIndex === ti && opts.armed.marker === m.marker;
      const lat = editable
        ? `<input class="lat-input" type="number" step="0.5" min="0" value="${m.latency_ms.toFixed(1)}"
                  data-mid="${m.id}" title="implicit time (ms) — Enter to apply">`
        : `${m.latency_ms.toFixed(1)}`;
      rows.push(`
        <tr class="${armed ? "armed" : ""}" data-ti="${ti}" data-marker="${m.marker}">
          <td><span class="eye-chip ${tr.label === "OS" ? "os" : "od"}">${tr.label}</span></td>
          <td><b class="mono mk ${editable ? "clickable" : ""}" data-ti="${ti}" data-marker="${m.marker}"
                 title="${editable ? "클릭 후 파형 위를 클릭해 커서 이동" : ""}">${m.marker}</b>
              ${m.is_auto === false ? `<span class="manual-tag" title="수동 배치">수동</span>` : ""}</td>
          <td class="num">${lat}</td>
          <td class="num">${m.amplitude_uv.toFixed(2)}</td>
          <td>${flagBadge(m.flag)}</td>
          ${editable ? `<td class="row-actions"><button class="icon-btn" data-del="${m.id}" title="마커 삭제">✕</button></td>` : ""}
        </tr>`);
    }
  });

  let tools = "";
  if (editable) {
    tools = `<div class="marker-tools">` + traces.map((tr, ti) => `
      <div class="marker-tool">
        <i class="dot ${tr.label === "OD" ? "od" : "os"}"></i><b>${tr.label}</b>
        <select class="add-marker-sel" data-ti="${ti}">
          ${(opts.markers || []).map((k) => `<option value="${k}">${k}</option>`).join("")}
        </select>
        <input class="add-marker-ms" data-ti="${ti}" type="number" step="0.5" min="0" placeholder="ms" style="width:76px">
        <button class="btn small" data-add="${ti}">+ 마커</button>
        <button class="btn small ghost" data-redetect="${ti}" title="모든 커서를 지우고 자동 검출을 다시 실행">↺ 자동검출</button>
      </div>`).join("") + `</div>`;
  }

  if (!rows.length) return `<p class="muted">검출된 마커가 없습니다 (No markers detected).</p>${tools}`;
  const ratios = n95p50Ratios(traces);
  const ratioLine = ratios.length
    ? `<p class="ratio-line">N95:P50 amplitude ratio · ${ratios.join(" · ")}</p>`
    : "";
  return `
    <div class="table-wrap"><table class="table compact marker-table">
      <thead><tr>
        <th>Eye</th><th>Marker</th><th class="num">Implicit <span class="unit">(ms)</span></th>
        <th class="num">Amp <span class="unit">(µV)</span></th><th>Status</th>${editable ? "<th></th>" : ""}
      </tr></thead>
      <tbody>${rows.join("")}</tbody>
    </table></div>${ratioLine}${tools}`;
}

/* Interocular (OD vs OS) comparison for one step, from /api/exams/{id}/analysis. */
function interocularTable(stepAnalysis) {
  const rows = (stepAnalysis && stepAnalysis.interocular) || [];
  if (!rows.length) return "";
  return `
    <details class="inter" ${rows.some((r) => r.flag !== "normal") ? "open" : ""}>
      <summary>양안 비교 (OD vs OS)
        ${rows.some((r) => r.flag === "abnormal") ? flagBadge("abnormal")
          : rows.some((r) => r.flag === "borderline") ? flagBadge("borderline") : flagBadge("normal")}
      </summary>
      <div class="table-wrap"><table class="table compact">
        <thead><tr><th>Marker</th><th>잠복기 차이</th><th></th><th>진폭비 (작은/큰)</th><th></th></tr></thead>
        <tbody>${rows.map((r) => `
          <tr>
            <td><b>${r.marker}</b></td>
            <td>${r.lat_diff_ms.toFixed(1)} ms${r.slower_eye && r.lat_flag !== "normal" ? ` <small class="muted">(${r.slower_eye} 지연)</small>` : ""}</td>
            <td>${flagBadge(r.lat_flag)}</td>
            <td>${r.amp_ratio.toFixed(2)}${r.smaller_eye && r.amp_flag !== "normal" ? ` <small class="muted">(${r.smaller_eye} 감소)</small>` : ""}</td>
            <td>${flagBadge(r.amp_flag)}</td>
          </tr>`).join("")}
        </tbody>
      </table></div>
      <p class="muted cap">기준(시연값): 잠복기 차이 &gt; ${rows[0].limits.lat_diff_border}/${rows[0].limits.lat_diff_abn} ms,
        진폭비 &lt; ${rows[0].limits.amp_ratio_border}/${rows[0].limits.amp_ratio_abn} → 경계/비정상 (마커별 상이)</p>
    </details>`;
}
