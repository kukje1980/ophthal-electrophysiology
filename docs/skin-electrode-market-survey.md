# ERG 피부(스킨) 전극 시장조사 및 추천 (2026-10)

> 목적: VEP처럼 각막에 닿지 않는 **피부 전극(lower-lid skin electrode)** 으로 ERG를 기록하는
> 제품·소모품 현황을 조사하고, 본 시스템(`ophthal-electrophysiology`) 및 병원 공급 관점에서 추천안을 정리한다.
> 조사 방법: 제조사 공식 스토어·규제 DB(FDA GUDID)·ISCEV 표준·2016~2026 비교 논문 웹 검색. 국내(식약처) 허가·가격은 웹에서 확인되지 않아 별도 확인 항목으로 남김.

## 1. 결론 요약

| 순위 | 추천 | 용도 | 근거 |
|---|---|---|---|
| **1** | **LKC Sensor Strip** (RETeval용, DIN 변환 케이블로 타 장비 연결 가능) | 소아·비협조 환자, 스크리닝(당뇨망막병증·약물독성), 플리커/LA ERG | 활성·기준·접지 3극 일체형 → 위치 재현성 최고. 2015년 이후 3,000대 보급, 200편+ 논문. 시판 피부 ERG 전극 중 유일하게 시판 가격·규제(FDA/MDR/Anvisa) 공개 |
| **2** | **범용 Ag/AgCl 소형 일회용 전극** (Ambu Neuroline 700/715 등 EEG/EMG용) | 기존 앰프(Grass·Roland·Diagnosys·DAQ)에 바로 연결, 비용 최소화 | 다수 비교 논문의 표준 피부 전극. 스냅/DIN 1.5 mm 터치프루프 등 범용 커넥터. 단가 수백 원대 |
| **3** | Diopsys ERG Lid Electrode (6020-0002-00) | Diopsys NOVA/ARGOS 보유 병원 전용 | 전용 소모품. 2025년 FCA(허위청구) 합의 $14.25M 이력 → 공급 리스크 |
| 참고 | Konan EvokeDx | 비독점(non-proprietary) 스냅 EEG 전극 사용 | 전용 소모품 없음. 범용 전극으로 ERG 피부 기록 가능 → 2순위와 동일 전략 |

**핵심 메시지**
- 피부 전극 ERG 진폭은 각막 전극(DTL·ERG-Jet) 대비 **대략 30~40 % 수준**(ffERG 약 60 % 감소, mfERG/PERG 약 60~70 % 감소). 파형 형태와 잠복시는 유지된다.
- 따라서 **피부 전극 전용 정상치(reference range)를 반드시 별도 구축**해야 한다(ISCEV: 참고 범위는 전극 특이적). 본 앱의 `/reference` 기능(실험실별 정상치)이 그 역할을 한다.
- 하안검 가장자리 **2 mm 아래** 위치가 표준이며, 10~20 mm 멀어지면 진폭이 유의하게 감소한다(잠복시는 무영향). 일체형 스트립이 이 오차를 줄여준다.
- 가장 안전한 임상 포지셔닝: **ffERG·플리커·PERG는 피부 전극 1차 선택, DTL/ERG-Jet은 PhNR 감쇠·고잡음·정밀 진단이 필요할 때 2차 선택**.

## 2. 배경: ISCEV 표준에서의 위치

- ISCEV ffERG 2022 표준은 활성 전극 접촉 위치로 **각막, 구결막, 하안검 피부** 세 가지를 명시한다. 피부 전극은 표준 안에 포함되지만 "진폭이 작고 신호 평균화가 필요할 수 있다", "참고 범위는 전극 특이적"이라고 경고한다.
- 피부 전극 임피던스 권고: 10~100 Hz에서 **≤ 5 kΩ**, 활성·기준 전극 임피던스는 비슷하게(2015 표준 명문, 본 앱 Live 페이지의 5 kΩ 경고와 일치).
- 2022 표준은 소아·비협조 환자용 **비표준 단축(abbreviated) 프로토콜**을 별도로 기술 → 피부 전극 + 단축 프로토콜 조합이 소아 ERG의 현실적 경로다.
- PERG: ISCEV 표준은 각막/결막 전극을 기본으로 하지만, 하안검 피부 컵 전극으로 양안 동시 기록하는 녹내장 연구(PERGLA 등)가 다수. 세션 내/간 변동계수 각 10 %/2 % 미만으로 보고. 단, 장기 추적에는 세션 간 변동이 크다는 2021년 보고가 있다.

## 3. 근거 논문(진폭 비교) 요약

| 연구 | 비교 | 결과 |
|---|---|---|
| Lapkovska 2016 (BMC Ophthalmol) | DTL vs Ambu Neuroline 725, Mini-Ganzfeld ffERG | DTL 진폭이 **최대 4배**. 둘 다 기록 가능, 별도 정상치 필요 |
| 2022 (Doc Ophthalmol) | DTL vs 금컵 피부 전극, mfERG | P1 진폭 **70 %+ 감소**, 협조 환자는 DTL 권고 |
| Nowitzki 2025 (Doc Ophthalmol) | DTL vs 피부, mfERG PhNR / mfPERG | 피부 진폭 PhNR 32~38 %, PERG 37~38 %; SNR 80 % / 60 % |
| 2025 (Prog Neuropsychopharmacol Biol Psychiatry) | DTL vs 피부, ffERG(정신과) | 진폭 약 **60 % 감소**, 양안 재현성 ICC > 0.75 |
| Hobby 2018 (Doc Ophthalmol, UCL) | RETeval Sensor Strip 위치 2 mm vs 10~20 mm | 멀어질수록 진폭 유의 감소(p<0.005), 피크 시간 무영향 |
| Zurich 2025 (Doc Ophthalmol) | RETeval 피부 전극 LA-ERG 재검사(45~65세 27명) | 재현성 확보, a-파 진폭 변동이 가장 큼 |
| SickKids 2018 | RETeval 소아 35명 | 진폭 ICC 0.82, 잠복시 ICC 0.53 |
| Mayo PuREC 2017 (일본) | 피부 전극 + 노이즈 제거 알고리즘 | 산동 없이 정상 성인 기록 가능 |
| Tomey LE-4000 2016 (일본) | 안와연(orbital rim) 피부 전극 + 감산 노이즈 제거 | 안검근 노이즈가 주 잡음원; 페이스트로 임피던스 < 5 kΩ |

## 4. 제품별 상세

### 4.1 LKC Technologies — Sensor Strip (RETeval)
- 구성: 좌/우안 전용 일회용 스트립, **활성·기준·접지 Ag/AgCl 3극 일체형**. 미국 특허 9,510,762.
- 규격: Regular / **Small(소아용, SKU 95-090)** 두 사이즈.
- 가격(LKC 공식 스토어, 2026-10 검색 기준): **50쌍 1박스 USD 899~1,099**(페이지마다 상이) → 쌍당 약 USD 18~22.
- 액세서리: Sensor Strip Lead USD 153, **Sensor Strip → DIN 케이블 USD 195**(RETeval이 아닌 일반 앰프의 DIN 1.5 mm 입력에 연결 가능), 소형 스트립 듀얼 케이블, 1→2 스플리터.
- 규제: FDA 510(k) K142567(GUDID 제품코드 GXY, Electrode, Cutaneous), EU MDR, Anvisa(2020). **식약처 허가·국내 대리점은 웹에서 미확인**.
- 장점: 위치 재현성, 접지 포함으로 전극 1개만 부착, 소아 사이즈 존재, 근거 논문 최다.
- 단점: 소모품 단가 높음(국산 범용 전극 대비 수십 배), 접착면이 넓어 눈 주위 민감 환자 불편 가능, 공급사 단일.

### 4.2 범용 Ag/AgCl 일회용 피부 전극 (Ambu Neuroline 700 / 715 / 725 등)
- Neuroline 700: Ambu 신경계 라인 중 **가장 작은** 자가접착·재부착 가능 전극 → 영유아·소아 안면 적용에 적합.
- Neuroline 715: 투명 센서부(정확한 위치 조준), 리드 50/80/120/200 cm 선택.
- Neuroline 725: 비교 논문에서 하안검 활성 전극으로 사용된 모델.
- 커넥터: 스냅 또는 DIN 1.5 mm 터치프루프 → Grass, Roland RETI-port, Diagnosys Espion, Konan EvokeDx, NI-DAQ 프런트엔드 등 **대부분의 앰프에 직결**.
- 비용: 쌍당 수천 원 이하(해외 유통가 기준; 국내가 미확인). 접지·기준 전극은 별도 부착 필요(3개/안).
- 국산 대체: Ag/AgCl 일회용 ECG/EEG 전극 국내 제조사 제품도 전기적으로 동등하나, **소아 안면용 소형 폼 전극**인지 확인 필요(웹 검색에서 소아 안면용 국산 라인은 확인되지 않음).

### 4.3 Diopsys — ERG Lid Electrode (6020-0002-00)
- Diopsys NOVA/ARGOS 전용 일회용 하안검 스트립(US 9,026,189). 전두부 접지 + 양측 하안검 센서 구성, 산동 불필요, 검사 10분.
- 회사 상태: 2022년 LumiThera에 인수, **2025년 미국 FCA 허위청구 합의 USD 14.25M**(NOVA 과잉 사용 유도 혐의). 공급·평판 리스크로 신규 도입 비추천.

### 4.4 Konan Medical — EvokeDx
- icVEP/VEP/ERG 플랫폼. 전극 리드가 **표준 스냅 커넥터** → 비독점 EEG 전극 사용 가능. FAQ: "ERG용 표준 EEG 피부 전극은 준비·부착이 쉽고 신호 진폭도 양호".
- 국제메디언스 취급 브랜드(Konan)라는 점에서, EvokeDx 보유 병원에는 **범용 전극(4.2) 번들**이 현실적 소모품 제안이다. (konanmedical.com은 이 세션 네트워크에서 차단되어 스펙 페이지 원문은 미확인.)

### 4.5 Diagnosys / Roland Consult / Metrovision
- Diagnosys: 카탈로그에 일회용 피부 전극(D161)이 있으나 **접지/기준 용도**로 분류. 활성 전극은 DTL Plus(1회용 실 전극)가 주력 → 피부 ERG는 범용 전극으로 운용.
- Roland RETI-port/scan 21: 전용 피부 ERG 전극 제품 없음. 금·백금·은 활성 전극 + 임의 기준 전극(FDA 설명) → 범용 전극 호환.
- Metrovision: 전극 호환 목록 웹 미확인.

### 4.6 일본 제품(참고)
- Mayo Corp. PuREC(이나자와), Tomey LE-4000(나고야): 피부 전극 + 소프트웨어 노이즈 제거(PURE 알고리즘)로 산동 없는 ffERG. 전용 전극이 아니라 **알고리즘**이 핵심 → 본 앱의 `filters.py`/평균화 로직에 반영할 아이디어(§6).

## 5. 비접촉(건식) VEP 전극 동향
- 사용자가 언급한 "비접촉식 VEP 전극"은 **건식(dry)/반건식 EEG 전극**(페이스트 없이 두피 접촉) 또는 **용량성(capacitive) 비접촉 전극**을 가리킨다.
  - Wearable Sensing DSI-VR300: 7채널 무선 건식 EEG, P300/VEP 용 설계(연구용).
  - 2026 Sci Rep: 반건식 헤드셋으로 VEP·P300 기록, 습식 대비 사용 가능 수준 결론.
  - 용량성 비접촉 전극은 특허·ECG 수준이며 VEP 상용 제품은 미확인. 2025 리뷰: 건식은 편의성↑, 신호 품질↓.
- **ERG에는 비접촉/건식 방식이 적용되기 어렵다.** ERG는 수 µV~수백 µV 신호를 안검 근육 잡음 위에서 기록하므로 젤 접착식 Ag/AgCl 피부 전극이 현실적 하한이다. "비접촉"의 ERG 대응물은 **각막 비접촉 = 하안검 피부 전극**으로 해석하는 것이 맞다.

## 6. 본 시스템에 대한 제안(소프트웨어)
1. **전극 타입 필드**를 검사(Exam)/정상치(reference_ranges)에 추가: `corneal_dtl`, `corneal_jet`, `skin_strip`, `skin_generic`. 판정 시 같은 전극 타입의 정상치만 사용(ISCEV 전극 특이적 정상치 요구 충족).
2. 피부 전극 선택 시 **스윕 수 자동 증가**(ffERG ×2, PERG ≥ 150, 플리커 ≥ 60)와 아티팩트 거부 임계 하향 → 진폭 60 % 감소·SNR 저하 보상.
3. Live 페이지 임피던스 경고를 전극 타입별로: 피부 전극은 ≤ 5 kΩ **및** 활성/기준 임피던스 차이 경고.
4. 일본식 노이즈 감산(안검근 EMG 성분 제거: 눈 깜빡임 구간 자동 제외 + 50/60 Hz 적응형 노치) 옵션.
5. 보고서에 "피부 전극 기록 — 각막 전극 정상치와 직접 비교 불가" 문구 자동 삽입.

## 7. 추천 실행안(사업)
| 단계 | 내용 |
|---|---|
| 1 | 식약처 의료기기 통합정보시스템에서 LKC "RETeval"/"Sensor Strip"(GXY), Ambu "Neuroline" 수입허가 여부·수입사 확인 |
| 2 | 미허가 시: Neuroline 700(소아)/715(성인) 또는 동급 국산 Ag/AgCl 소형 전극을 **ERG 피부 전극 키트**(활성·기준·접지 3매 + 피부 준비제 + 위치 가이드 카드)로 구성 → 즉시 공급 가능, 단가 최저 |
| 3 | LKC와 Sensor Strip 단독 수입(DIN 케이블 포함) 협의 → RETeval 없는 병원도 기존 앰프에 연결 가능하다는 점을 세일즈 포인트로 |
| 4 | 파일럿 병원 1~2곳에서 정상인 20~30명 양 전극 동시 기록 → 전극별 정상치 구축(본 앱 `/reference` CSV 업로드) → 임상 도입 |
| 5 | 소모품 가격표: Sensor Strip 쌍당 약 USD 20(수입 원가 전) vs 범용 전극 3매 수천 원 → 병원 규모별 제안 |

## 8. 미확인·주의 사항
- 식약처 허가, 국내 대리점, 국내 가격은 모두 **웹에서 확인되지 않음**(직접 조회 필요).
- LKC·Diagnosys·Konan·MDPI·PMC 사이트는 이 세션의 네트워크 정책으로 직접 열 수 없어 검색 스니펫 기준으로 정리함. 가격은 발주 전 재확인.
- PERG는 ISCEV 2024 표준상 각막/결막 전극이 기본이므로, 피부 전극 PERG 결과는 "ISCEV 비표준"으로 보고서에 명시해야 한다.

## 출처
- LKC 스토어: https://store.lkc.com/reteval-sensor-strip-electrodes/ , https://store.lkc.com/small-sized-sensor-strips-box-of-50-pairs/ , https://store.lkc.com/sensor-strip-to-din-cable/ , https://store.lkc.com/sensor-strip-lead/
- LKC RETeval 소개·보급 현황: https://lkc.com/reteval-us-od/ , https://lkc.com/new/reteval-handheld-erg-vep-device-referenced-in-200-publications/
- GUDID RETeval/Sensor Strip(GXY, K142567): https://accessgudid.nlm.nih.gov/devices/10857901006009
- Sensor Strip 특허 뉴스: https://www.fdanews.com/articles/174068-lkc-technologies-introduces-reteval-complete-device
- Anvisa 승인: https://www.biospace.com/lkc-technologies-announces-brazilian-health-regulatory-agency-approval-for-the-reteval-device-and-associated-sensor-strip-electrodes
- Hobby 2018 전극 위치: https://link.springer.com/article/10.1007/s10633-018-9652-z
- Zurich 2025 재현성: https://link.springer.com/article/10.1007/s10633-025-10065-8
- Nowitzki 2025 DTL vs 피부 mfERG/mfPERG: https://pubmed.ncbi.nlm.nih.gov/40205293/
- 2025 정신과 ffERG 피부 전극 검증: https://www.sciencedirect.com/science/article/pii/S0278584625000594
- 2022 mfERG 금컵 vs DTL: https://pubmed.ncbi.nlm.nih.gov/36536110/
- Lapkovska 2016 DTL vs Neuroline: https://bmcophthalmol.biomedcentral.com/articles/10.1186/s12886-016-0311-4
- ISCEV ffERG 2022: https://link.springer.com/article/10.1007/S10633-022-09872-0
- 피부 전극 ffERG 정상 성인(브라질): https://www.scielo.br/j/abo/a/WzYHwp4YccRFhYzgLzFMS7j/?lang=en
- Mayo PuREC 2017: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5496106/
- Tomey LE-4000 노이즈 감소: https://link.springer.com/article/10.1007/s10792-016-0240-5
- 2026 휴대형 ERG 리뷰(Biomedicines): https://www.mdpi.com/2227-9059/14/2/384
- Diopsys 전극 특허·GUDID: https://patents.google.com/patent/US9026189 , https://accessgudid.nlm.nih.gov/devices/00850514007046
- Diopsys 인수·합의: https://crstoday.com/news/lumithera-completes-acquisition-of-diopsys/2480675/ , https://www.bioworld.com/articles/718871-diopsys-agrees-to-14m-settlement-over-fca-allegations
- Konan EvokeDx: https://www.konanmedical.com/evokedx/specs-faq
- Diagnosys 전극 카탈로그: https://www.diagnosysllc.com/electrodes-for-clinical-practice/
- Roland RETI-port/scan 21: https://roland-consult.de/reti-port-scan-21.html , https://accessgudid.nlm.nih.gov/devices/04260157780231
- Ambu Neuroline: https://ambu.com/neurology/emg-electrodes/product/ambu-neuroline-700 , https://ambu.com/neurology/emg-electrodes/product/ambu-neuroline-715
- PERG 피부 전극(PERGLA): https://pmc.ncbi.nlm.nih.gov/articles/PMC2760457 , 2021 추적 변동성: https://link.springer.com/article/10.1007/s10633-021-09854-8
- 건식 VEP: https://wearablesensing.com/products/ , https://www.nature.com/articles/s41598-026-52672-8
