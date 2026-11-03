# ERG/VEP 앰프 추천: 노이즈에 강하고 본 프로그램에 바로 쓸 수 있는 것 (2026-11)

> 질문: "어떤 앰플리파이어를 써야 노이즈에 강하고 프로그램에 바로 적용해서 쓸 수 있는가."
> 방법: ① 본 저장소의 수집 계층(`app/acquisition/`)을 읽고 드라이버마다 **실제로 녹화(트리거 평균)까지 되는지** 확인,
> ② 제조사 페이지·FDA 510(k)/GUDID·조달 문서를 웹으로 검색. 제조사 사이트(biosemi.com, gtec.at, roland-consult.de, iscev.org)는
> 이 세션의 네트워크 정책으로 직접 열리지 않아 **검색 결과 요약 기준**으로 정리했다. 사양은 발주 전에 데이터시트로 다시 확인해야 한다.

## 1. 결론 요약

| 목적 | 추천 구성 | 프로그램 연동 | 노이즈 | 의료기기 |
|---|---|---|---|---|
| **지금 바로, 코드 수정 없이** | **절연형 아날로그 환자용 생체증폭기 + NI USB-6215 (절연형 DAQ)** → `nidaq` 드라이버 | **즉시 사용 가능.** 양안(OD/OS) 동시 기록, 트리거, 차동 입력, CAL 게인 보정, 장치 찾기 도우미까지 구현됨 | 앰프 성능에 좌우됨. 아날로그 케이블·접지 루프 관리 필요 | 앰프 기종에 따름 |
| **새로 구매, 노이즈·임상 사용 균형 최상** | **g.tec g.USBamp (의료용 버전)** | `lsl` 드라이버 보강 필요(다채널 + 트리거, 반나절 규모) | **< 0.4 µV rms (1–30 Hz)**, 24-bit, 8 bipolar 채널 | **FDA 510(k) K060803** (의료용 버전). *RESEARCH 버전은 비의료* |
| **연구용, 노이즈 성능 최고** | **BioSemi ActiveTwo** (능동 전극 + CMS/DRL) | `biosemi-tcp` 드라이버 수정 필요(채널·스케일·트리거) | 0.8–2.0 µV rms, CMRR 150–160 dB @ 50 Hz(ABR 구성), LSB 31.25 nV | 연구용 |

**한 줄 추천**
- 이미 Grass(P511/CP511/Model 15) 같은 아날로그 앰프가 있으면 **NI USB-6215만 사서 `nidaq`로 오늘 바로** 쓴다.
- 새로 산다면 **g.USBamp 의료용 버전**을 고르고 `lsl` 드라이버를 보강한다. 노이즈 내성, 의료기기 허가, ERG 몽타주(안구별 bipolar), 소프트웨어 연동을 모두 만족하는 유일한 후보다.

## 2. 본 프로그램에서 실제로 되는 것(코드 확인 결과)

Live 페이지는 **트리거가 들어와야 에포크를 자르고 평균**한다(`app/routers/live.py:88-98`). 트리거는 시뮬레이터의 주기 트리거
또는 드라이버가 채우는 `last_triggers`로만 들어온다. 이 기준으로 각 드라이버를 보면 다음과 같다.

| 드라이버 | 양안 OD/OS | 트리거 | 필터 | 녹화(평균) | 비고 |
|---|---|---|---|---|---|
| `nidaq` | **O** (채널 여러 개, `eyes=`) | **O** (아날로그 TTL 채널, 상승/하강 에지) | notch, hp, `diff=1` | **O** | `GET /api/live/daq` 장치 찾기, CAL 게인 보정, 벤치 점검까지 완비 |
| `lsl` | X: 채널 0만 반환 (`hw_streams.py:59`) | X: 마커 스트림·트리거 채널 미처리 | X | **X** (화면 표시만) | README의 "functional"은 표시까지만 해당 |
| `biosemi-tcp` | X: 채널 0만 | X: Status(트리거) 채널 미해석 | X | **X** | 스케일 의심: 코드는 `2000/2^23 µV`(≈0.24 nV/bit), BioSemi 공식 LSB는 **31.25 nV** → 약 131배 작게 표시될 수 있음(`hw_streams.py:107`, 실측 확인 필요) |
| `serial-csv` | X: 1채널 | X | X | **X** | |
| `gtec` / `ced` | 스켈레톤 | - | - | **X** | SDK 연결 코드 없음 |
| 스윕 방식 `HardwareDevice` (Acquire 화면) | 스켈레톤 | - | - | **X** | `hardware.py`의 TODO만 있음 |

→ **"코드 수정 없이 바로" 환자 기록이 가능한 실제 장비 경로는 `nidaq` 하나뿐이다.**
디지털 앰프(BioSemi·g.tec·Brain Products 등)는 노이즈 면에서 유리하지만, 드라이버를 보강해야 녹화까지 된다.

## 3. "노이즈에 강하다"는 무엇으로 결정되나

ERG는 수십~수백 µV, PERG는 2–8 µV, VEP는 5–20 µV다. 앰프 자체의 입력 잡음(0.4–2 µV)은 평균화(√N)로 충분히 줄어든다.
임상에서 실제로 기록을 망치는 잡음원과, 이를 막는 앰프 특성은 다음과 같다.

| 실제 잡음원 | 막는 앰프 특성 | 아날로그+DAQ | 디지털 24-bit 앰프 |
|---|---|---|---|
| 전원 험(국내 60 Hz), 특히 전극 임피던스가 안구별로 다를 때 | 높은 CMRR, **DRL/CMS(능동 접지)**, 능동 전극 | 앰프 CMRR에만 의존 | DRL·능동 실딩으로 유리 |
| BNC 케이블·PC USB 접지 루프 | 환자 근처에서 디지털화, 절연 | **루프 위험 있음** → 절연 DAQ·차동 입력으로 완화 | 케이블 구간이 디지털이라 거의 없음 |
| 눈 깜빡임 후 포화·회복 지연(스윕 손실) | 넓은 동적 범위, DC 결합 | AC 결합 앰프는 포화 후 회복 지연 | 24-bit DC 결합이라 포화가 드묾 |
| 단계별 게인 전환 실수(µV 스케일 오류) | 고정 게인 | 앰프 게인과 연결 문자열 `gain=`을 **둘 다** 맞춰야 함 | 게인 전환 자체가 없음 |
| 근전도·움직임 | (앰프보다 전극·환자 준비·아티팩트 거부) | 동일 | 동일 |

**노치 필터는 마지막 수단으로 쓴다.** 노치는 플래시 직후 과도 신호에 링잉을 만들 수 있다. 험은 CMRR, 접지, 전극 임피던스(< 5 kΩ, 활성·기준 비슷하게)로 먼저 잡는다.
본 앱의 Live(`nidaq`) 경로는 노치를 기본으로 끄고, `;notch=60`을 줄 때만 적용한다.

## 4. 후보별 상세

### 4.1 [즉시] 아날로그 환자용 앰프 + NI USB-6215 (`nidaq`)

**DAQ: NI USB-6215 권장.** 16 AI(16-bit, 250 kS/s), USB 버스 전원, **채널-접지 60 V 절연(CAT I)**.
같은 계열의 비절연 모델(USB-6211/6212)보다 PC USB 접지 루프를 끊어주므로 노이즈 면에서 이 모델을 고른다.
단, 이 절연은 **환자 절연이 아니다.** 환자 안전(IEC 60601-1 BF/CF 등급)은 앰프가 책임져야 한다.
Linux/Mac용 파트(780105-01)는 일부 유통처에서 단종으로 표시되므로 표준 파트(779677-01)로 주문한다.

16-bit여도 문제없다. ±10 V 레인지와 게인 ×5,000이면 입력 환산 LSB가 약 60 nV다. DAQ 잡음도 입력 환산 0.05 µV 수준(사양서 확인)이라 앰프 잡음보다 한 자릿수 작다.

**앰프 후보**

| 앰프 | 상태 | 비고 |
|---|---|---|
| **Grass P511 / CP511 / Model 15** (Natus) | Natus가 Grass 제품군을 인수(USD 18.6M). 신품 구매 가능 여부는 웹에서 확인 안 됨 | 본 앱 README·드라이버가 이 조합을 기준으로 작성됨. **보유 장비가 있으면 1순위** |
| **Digitimer D360** | 8채널 **절연형 환자용** 앰프(이탈리아 대학 조달 문서). Digitimer 인체용 제품군은 CE·FDA 등록 | 신규 구매 시 아날로그 경로의 유력 후보. 잡음·CMRR·개별 허가 번호는 **데이터시트 확인 필요** |
| A-M Systems Model 1700 | 4채널 차동 AC, 잡음 1.0 µVpp (10 Hz–10 kHz) | **연구(동물·세포)용.** 환자 절연·인체 사용 근거를 찾지 못함 → 환자 기록에는 비추천 |

**배선·설정(노이즈 최소화)**
1. 앰프 BNC 출력 OD → `ai0`, OS → `ai1`. **`diff=1`**로 차동 입력(BNC 심선 → AI+, 실드 → AI−).
   앰프 출력이 배터리·절연으로 플로팅이면 AI−와 AI GND 사이에 10–100 kΩ 바이어스 저항을 단다(NI 표준 권고).
2. 자극기 TTL → `ai7`(단일 종단, 코드가 자동 처리). 액티브 로우면 `edge=fall`.
3. **게인을 한 값으로 고정**한다(예: 앰프 ×5,000, DAQ `range=10` → 입력 ±2 mV). ffERG부터 PERG까지 바꾸지 않는다.
   단계마다 앰프 게인을 바꾸면 연결 문자열의 `gain=`도 바꿔야 하고, 놓치면 µV 값이 틀린다.
4. 앰프 쪽 HP 0.3 Hz / LP 300 Hz(OP·ffERG). 앱 쪽은 `hp=0.3`만 켜고, 노치는 험이 남을 때만 켠다.
5. 노트북은 가능하면 배터리로 운용하고, BNC는 짧게 묶어서 배선한다.

연결 문자열 예시(Live 페이지 **DAQ 연결 도우미**가 자동 생성):

```text
Dev1/ai0,Dev1/ai1@2000;gain=5000;trig=Dev1/ai7;thr=1.0;diff=1;hp=0.3;range=10
```

설치 후에는 **장비 점검**으로 확인한다. 채널별 RMS·60 Hz 성분, 트리거 간격 지터를 보고, CAL 측정 → *게인 보정 적용*으로 실제 게인을 맞춘다.

### 4.2 [신규 구매 1순위] g.tec g.USBamp (의료용 버전)
- 사양(제조사·FDA 문서): **16 monopolar / 8 bipolar(소프트웨어 선택)**, 24-bit, 입력 잡음 **< 0.4 µV rms (1–30 Hz)**.
  FDA 문서상 수치는 < 0.35 µV rms, < 2 µVpp.
- 허가: **FDA 510(k) K060803** (physiological signal amplifier, 21 CFR 882.1835, GUDID EBCI0216US0).
  **주의:** "g.USBamp RESEARCH"는 제조사가 비의료(연구 전용)로 명시한다. 환자 진료에 쓰려면 **의료용 버전을 지정해 구매**해야 한다. 식약처 허가는 확인 안 됨.
- ERG에 맞는 이유: 안구별 bipolar(활성-기준) 몽타주를 그대로 구성할 수 있다. 소프트웨어 접근 경로는 g.NEEDaccess(C/.NET/MATLAB/Python API)와 LSL 지원(제조사 표기)이다.
  DTL 전극의 1.5 mm 터치프루프 커넥터 직결 여부와 디지털 트리거 입력 사양은 데이터시트로 확인한다.
- 프로그램 작업: `lsl` 드라이버에 다채널 반환과 트리거(마커 스트림 또는 트리거 채널 에지 검출, `nidaq`의 `_edges` 재사용)를 추가하면 바로 녹화된다(§5).

### 4.3 [연구용 최고 성능] BioSemi ActiveTwo
- 능동 전극 + **CMS/DRL**: 제조사는 DRL을 측정 전극에서 멀리 둘 때 CMRR이 가장 좋다고 설명한다. CMRR 150–160 dB @ 50 Hz(ABR 구성, 가격표 기준).
  잡음은 샘플링에 따라 0.8–2.0 µV rms, **LSB 31.25 nV**(입력 범위 512 mVpp).
- 단점: 연구용(의료기기 아님). ERG의 DTL 같은 수동 전극을 쓰면 능동 전극의 장점이 줄어든다.
- 프로그램 작업: `biosemi-tcp`의 채널 선택, Status 채널 트리거 해석, **스케일(31.25 nV/bit)**을 수정해야 한다. 또는 LSL로 받는다(§5).

### 4.4 참고
- **Brain Products BrainAmp ExG**: 8 bipolar(+8 AUX), DC/AC 전환, 입력 잡음 ≤ 2 µVpp, CMRR ≥ 100 dB. 제조사 표기상 **의료기기 아님**. BrainVision LSL Connector(BrainAmp용)를 제공한다.
- **TMSi SAGA 32+/64+**: 듀얼 bipolar 입력 2개. Artinis가 인수했다. LSL·잡음 사양은 확인 안 됨.
- **OpenBCI Cyton 등 저가 보드**: 개발·벤치 테스트용으로는 쓸 만하다(LSL). 환자 기록용으로는 비추천.

## 5. 디지털 앰프를 쓰려면 필요한 코드 작업(예상 규모)

| 작업 | 파일 | 내용 | 규모 |
|---|---|---|---|
| LSL 다채널 | `app/acquisition/hw_streams.py` `LSLSampleStream` | `;ch=1,2;eyes=OD,OS;scale=` 옵션, `(signals, n)` 반환 | 소 |
| LSL 트리거 | 동상 | ① 데이터 스트림 안의 트리거 채널 에지 검출(`NiDaqSampleStream._edges` 재사용) ② 별도 마커 스트림의 타임스탬프 → 샘플 인덱스 변환 | 중 |
| BioSemi TCP | `BioSemiTcpStream` | 채널 선택, Status 채널 트리거 비트, 31.25 nV/bit 스케일 | 소 |
| 필터 공용화 | `filters.py` | `nidaq`의 notch/hp 체인을 모든 스트림에 적용 | 소 |
| 테스트 | `tests/test_live.py` | 가짜 inlet으로 다채널·트리거 정렬 검증 | 소 |

LSL을 보강하면 g.tec, Brain Products, ANT Neuro, OpenBCI 등 LSL을 지원하는 앰프를 한 번에 쓸 수 있다.

## 6. 구매 전 확인 목록
1. **식약처 허가**: 이번 조사의 어떤 앰프도 국내 허가를 웹에서 확인하지 못했다. 의료기기 통합정보시스템에서 직접 조회해야 한다.
2. **환자 절연 등급**: IEC 60601-1 BF/CF 등급을 데이터시트로 확인한다. NI DAQ의 60 V 절연은 환자 절연이 아니다.
3. **입력 사양**: 입력 임피던스(≥ 10 MΩ급), CMRR(≥ 100 dB), HP ≤ 0.3 Hz와 LP ≥ 300 Hz 설정 가능 여부, DC 결합 여부.
4. **전극 커넥터**: DTL·피부 전극의 1.5 mm 터치프루프(DIN 42802)를 바로 꽂을 수 있는지.
5. **트리거 입력**: 자극기 TTL을 받아 데이터와 같은 시간축에 기록하는지(채널 또는 마커).
6. **소프트웨어 인터페이스**: LSL·Python API 제공 여부와 라이선스.

## 출처
- Natus의 Grass 제품군 인수: https://www.fenwick.com/insights/experience/fenwick-represents-natus-medical-in-18-6-million-acquisition-of-grass-technologies-product-group-from-astro-med
- Digitimer D360 (조달 문서): https://www.dnisc.unich.it/documenti/__0__uda/__4187__dnisc/Avvisi/Avviso_2022_06_07/Relazione%20Tecnica.pdf
- A-M Systems Model 1700: https://www.medical-xprt.com/products/model-1700-differential-ac-amplifier-863431 , 매뉴얼 https://neurophysics.ucsd.edu/Manuals/A-M%20Systems,%20Inc/Four-Channel%20Differential%20AC%20Amplifier.pdf
- NI USB-6215: https://www.ni.com/en-us/support/model.usb-6215.html , https://kr.element14.com/ni-emerson/780105-01/usb-6215-multifunction-i-o-device/dp/3621651
- g.USBamp: https://www.gtec.at/product/gusbamp-research-16-channel-biosignal-amplifier/ , FDA K060803 https://fda.innolitics.com/device/K060803 , K123255 https://fda.innolitics.com/device/K123255 , GUDID https://accessgudid.nlm.nih.gov/devices/EBCI0216US0
- BioSemi ActiveTwo: https://biosemi.com/activetwo_full_specs.htm , https://biosemi.com/download/BioSemi%20Pricelist%202026.pdf , https://biosemi.com/faq/cms&drl.htm
- Brain Products BrainAmp: https://www.brainproducts.com/solutions/brainamp/ , LSL 도구 https://pressrelease.brainproducts.com/brainvision-lsl-tools/
- TMSi SAGA: https://uk.mathworks.com/products/connections/product_detail/saga32-64.html
- ISCEV ERG Standard 1999 (피부 전극 ≤ 5 kΩ): https://www.iscev.org/standards/pdfs/ISCEV-ERG-Standard-1999.pdf
