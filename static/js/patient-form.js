/* Ophthalmic patient record — one field spec drives the create form, the
   edit form and the read-only detail view, so they never drift apart. */

const SEL = {
  sex: [["M","남 (M)"],["F","여 (F)"],["O","기타 (O)"]],
  insurance: [["건강보험","건강보험"],["의료급여","의료급여"],["자동차보험","자동차보험"],
    ["산재보험","산재보험"],["일반","일반(비급여)"],["기타","기타"]],
  smoking: [["비흡연","비흡연"],["과거흡연","과거흡연"],["현재흡연","현재흡연"]],
  lens: [["phakic","유수정체 (phakic)"],["pseudophakic","인공수정체 (pseudophakic)"],
    ["aphakic","무수정체 (aphakic)"]],
};

/* t: text | date | number | select | bool | textarea ; span:2 = full width */
const PATIENT_GROUPS = [
  { title: "인적사항", fields: [
    { n:"mrn", l:"등록번호 (MRN)", t:"text", req:true },
    { n:"name", l:"성명", t:"text", req:true },
    { n:"name_en", l:"영문명", t:"text" },
    { n:"national_id", l:"주민등록번호", t:"text", ph:"000000-0000000" },
    { n:"birth_date", l:"생년월일", t:"date" },
    { n:"sex", l:"성별", t:"select", opt:SEL.sex },
  ]},
  { title: "연락처", fields: [
    { n:"phone", l:"휴대폰", t:"text", ph:"010-0000-0000" },
    { n:"email", l:"이메일", t:"text" },
    { n:"address", l:"주소", t:"text", span:2 },
    { n:"guardian_name", l:"보호자", t:"text" },
    { n:"guardian_relation", l:"관계", t:"text" },
    { n:"guardian_phone", l:"보호자 연락처", t:"text" },
  ]},
  { title: "접수 · 보험 · 의뢰", fields: [
    { n:"insurance_type", l:"보험유형", t:"select", opt:SEL.insurance },
    { n:"insurance_no", l:"보험(증)번호", t:"text" },
    { n:"referring_doctor", l:"의뢰의", t:"text" },
    { n:"referral_clinic", l:"의뢰기관", t:"text" },
    { n:"chief_complaint", l:"주호소 (C.C.)", t:"text", span:2 },
  ]},
  { title: "과거력", fields: [
    { n:"diabetes", l:"당뇨 (DM)", t:"bool" },
    { n:"diabetes_years", l:"당뇨 유병기간 (년)", t:"number" },
    { n:"hypertension", l:"고혈압 (HTN)", t:"bool" },
    { n:"smoking", l:"흡연", t:"select", opt:SEL.smoking },
    { n:"systemic_history", l:"기타 전신질환", t:"textarea", span:2 },
    { n:"medications", l:"복용 약물", t:"textarea", span:2 },
    { n:"allergies", l:"알레르기", t:"text", span:2 },
    { n:"family_ocular_history", l:"가족 안과력 (녹내장·망막색소변성 등)", t:"textarea", span:2 },
    { n:"ocular_history_od", l:"안과 과거력 · OD", t:"textarea" },
    { n:"ocular_history_os", l:"안과 과거력 · OS", t:"textarea" },
  ]},
  { title: "안과 기저검사", fields: [
    { n:"va_od", l:"교정시력 OD", t:"text", ph:"예: 1.0 / 0.5 / CF" },
    { n:"va_os", l:"교정시력 OS", t:"text" },
    { n:"refraction_od", l:"굴절값 OD", t:"text", ph:"예: -2.00 -0.75 x180" },
    { n:"refraction_os", l:"굴절값 OS", t:"text" },
    { n:"iop_od", l:"안압 OD (mmHg)", t:"number" },
    { n:"iop_os", l:"안압 OS (mmHg)", t:"number" },
    { n:"lens_status_od", l:"수정체 OD", t:"select", opt:SEL.lens },
    { n:"lens_status_os", l:"수정체 OS", t:"select", opt:SEL.lens },
    { n:"pupil_od", l:"동공 OD", t:"text", ph:"예: 8mm (산동)" },
    { n:"pupil_os", l:"동공 OS", t:"text" },
  ]},
  { title: "비고", fields: [
    { n:"note", l:"비고", t:"textarea", span:2 },
  ]},
];

const YN = [["true","있음"],["false","없음"]];
const _esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
  .replace(/>/g,"&gt;").replace(/"/g,"&quot;");

function _field(f, val) {
  val = (val == null) ? "" : val;
  const span = f.span === 2 ? " span2" : "";
  let ctrl;
  if (f.t === "select" || f.t === "bool") {
    const opts = f.t === "bool" ? YN : f.opt;
    ctrl = `<select name="${f.n}"><option value="">-</option>` +
      opts.map(([v,l]) => `<option value="${v}"${String(val)===v?" selected":""}>${l}</option>`).join("") +
      `</select>`;
  } else if (f.t === "textarea") {
    ctrl = `<textarea name="${f.n}" rows="2">${_esc(val)}</textarea>`;
  } else {
    const type = f.t === "date" ? "date" : f.t === "number" ? "number" : "text";
    ctrl = `<input name="${f.n}" type="${type}"${f.t==="number"?' step="any"':''} ` +
      `value="${_esc(val)}" placeholder="${_esc(f.ph||"")}"${f.req?" required":""}>`;
  }
  return `<label class="pfield${span}"><span>${f.l}${f.req?' <em>*</em>':''}</span>${ctrl}</label>`;
}

/* Build a create/edit form into `formEl`; `values` prefills (edit mode). */
function renderPatientForm(formEl, values, submitLabel) {
  formEl.innerHTML = PATIENT_GROUPS.map(g =>
    `<fieldset class="pfs"><legend>${g.title}</legend>
       <div class="pgrid">${g.fields.map(f => _field(f, values && values[f.n])).join("")}</div>
     </fieldset>`).join("") +
    `<div class="pactions">
       <button class="btn primary" type="submit">${submitLabel || "환자 등록"}</button>
       <span class="msg" data-msg></span>
     </div>`;
}

/* Collect a typed object from the form, omitting empty fields. */
function collectPatientForm(formEl) {
  const out = {};
  for (const g of PATIENT_GROUPS) for (const f of g.fields) {
    const el = formEl.elements[f.n];
    if (!el) continue;
    let v = el.value;
    if (v === "" || v == null) continue;
    if (f.t === "number") { v = Number(v); if (Number.isNaN(v)) continue; }
    else if (f.t === "bool") v = (v === "true");
    out[f.n] = v;
  }
  return out;
}

/* Render a read-only grouped view; hides empty fields and empty groups. */
function renderPatientView(containerEl, p) {
  containerEl.innerHTML = PATIENT_GROUPS.map(g => {
    const rows = g.fields.filter(f => p[f.n] != null && p[f.n] !== "").map(f => {
      let v = p[f.n];
      if (f.t === "bool") v = v ? "있음" : "없음";
      else if (f.t === "select") {
        const o = f.opt.find(x => x[0] === String(v));
        v = o ? o[1] : v;
      }
      return `<div class="pv"><dt>${f.l}</dt><dd>${_esc(String(v))}</dd></div>`;
    });
    if (!rows.length) return "";
    return `<section class="card pcard"><h3 class="pgh">${g.title}</h3>
      <dl class="pvlist">${rows.join("")}</dl></section>`;
  }).join("");
}
