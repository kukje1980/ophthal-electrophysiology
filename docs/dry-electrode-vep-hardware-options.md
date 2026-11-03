# 건식 전극 VEP 구현: 사용 가능한 전극과 앰프 확인 (2026-11)

> 질문: 건식 전극으로 VEP를 구현할 때 실제로 조합 가능한 전극과 앰프(또는 프런트엔드 칩)는 무엇인가.
> 조사 기준: 제조사 데이터시트·규제 DB(FDA 510(k)/GUDID)·리뷰 논문. 가격은 공개된 것만. ERG는 건식이 불가하므로 VEP 중심(§7 참조).

## 1. 결론 요약

| 목적 | 전극 | 앰프 | 앱 연동 |
|---|---|---|---|
| **임상 등급(CE/FDA 의료기기)** | g.tec **g.SAHARA hybrid**(능동 건식, 8핀 7 mm, 젤 유무 겸용) | g.tec **g.USBamp**(+g.SAHARAbox) 또는 **g.Nautilus PRO 16ch SAHARA**(무선) | LSL → `lsl` 드라이버. **트리거 채널 처리 추가 필요(§6)** |
| 임상 등급, 캡 형태 | ANT Neuro **waveguard touch**(Ag/AgCl 폴리머 건식, 8/32/64ch) | ANT **eego mylab**(>1 GΩ, 8-bit TTL 트리거) / **eego 8**(2-bit TTL) | 미국·캐나다는 연구용 한정. LSL 가능 |
| **연구·파일럿(저가)** | OpenBCI **Ultracortex 콤형 Ag/AgCl** 수동 건식 또는 Florida Research Instruments 건식 핀 | **OpenBCI Cyton**(ADS1299, 8ch USD 1,249 / 16ch USD 2,499) | GUI Networking→LSL. 트리거는 D11~D18 디지털 입력(LSL에 기본 포함 안 됨) |
| 초저가 데모 | g.tec **Unicorn Hybrid** 전극(건식/젤 겸용) | **Unicorn Hybrid Black**(8ch, 24-bit, **250 Hz**) | UnicornLSL. 250 Hz는 ISCEV VEP 샘플링 권고에 미달 → 데모 한정 |
| **자체 제품 설계** | **Datwyler SoftPulse**(Ag/AgCl 코팅 전도성 엘라스토머, OEM) 또는 금도금 핀 + 능동 버퍼(**LMP7721**, 3 fA) | **TI ADS1299**(24-bit 8ch, 1 GΩ, 300 pA, 1 µVpp, CMRR −110 dB, 6 nA 리드오프 임피던스 측정) | 시리얼/LSL로 앱 연결. IEC 60601-1·80601-2-26 인증 경로 필요 |

핵심: 건식 전극의 접촉 임피던스는 **100 kΩ~2 MΩ**(습식 <5 kΩ)이라, 앰프 입력임피던스 **≥1 GΩ**, 입력 바이어스 전류 수백 pA 이하, 능동 전극(전극 바로 뒤 버퍼) 또는 능동 실딩, CMRR ≥100 dB, TTL 트리거 입력이 모두 있어야 VEP 평균화가 가능하다. 위 표의 조합은 모두 이 조건을 만족한다(Unicorn은 샘플링만 예외).

## 2. 건식 VEP 앰프의 필수 조건

| 항목 | 요구값 | 근거·비고 |
|---|---|---|
| 전극 접촉 임피던스(건식) | 100 kΩ ~ 2 MΩ(상용 건식), 신형 65 kΩ 이하 | A*STAR 건식 전극 개발 보고. 습식 ISCEV 기준 <5 kΩ는 적용 불가 |
| 앰프 입력임피던스 | ≥1 GΩ(DC), 50 Hz에서 수백 MΩ 이상 | BioSemi: 10¹² Ω ∥ 11 pF → 50 Hz에서 300 MΩ. 입력 커패시턴스가 실질 한계 |
| 입력 바이어스 전류 | ≤ 수백 pA(수동 건식) / fA급(능동 버퍼) | 1 MΩ × 300 pA = 0.3 mV 오프셋(허용). INA116(3 fA)는 TI NRND → LMP7721 대체 |
| 능동 전극 / 실딩 | 필수에 가까움 | 능동 전극의 낮은 출력임피던스가 케이블 움직임 아티팩트를 억제(Xu 2017 리뷰). ANT는 능동 실딩으로 고임피던스에서도 동작 |
| CMRR | ≥100 dB | EEG 프런트엔드 일반 요구. ADS1299 −110 dB |
| 잡음 | ≤1 µVpp(0.01~70 Hz) | VEP P100 진폭 5~20 µV 대비 |
| 임피던스 측정 | MΩ 범위 측정 가능 | ADS1299 리드오프 전류원 6 nA 방식, g.tec·Brain Products LED 표시 |
| 트리거 | TTL 디지털 입력 또는 LSL 마커 | VEP 평균 64~100회의 자극 동기. 지터 ≤1 ms |
| 샘플링 | ≥500 Hz(권고 1 kHz) | ISCEV VEP 2025 권고. Unicorn 250 Hz는 미달 |
| 규제 | IEC 60601-1, IEC 80601-2-26(EEG 특정) | 임상 사용 시. 건식 전극·앰프 비교 리뷰(IEEE Sensors J 2020)가 이 기준으로 평가 |

## 3. 전극 옵션

### 3.1 능동 건식(제조사 앰프에 종속)
| 전극 | 제조사 | 사양 | 호환 앰프 | 비고 |
|---|---|---|---|---|
| **g.SAHARA hybrid** | g.tec(오스트리아) | 8핀, 핀 길이 7 mm, 금합금, 능동, 2핀 안전 커넥터, 1.5 kV 보호 케이블. **젤 없이/젤과 함께** 모두 사용 | g.HIamp(직결), g.USBamp(+**g.SAHARAbox**), g.Nautilus PRO/Research/Multi-Purpose, g.GAMMAcap 장착 | 제조사가 SSVEP·c-VEP 용도 명시. 비교연구에서 SSVEP 진폭이 타 시스템보다 작았다는 보고 |
| **actiCAP Xpress Twist** | Brain Products(독일) | 금도금 팁, 길이·형상 다양, 능동 건식 8/16/32ch | BrainAmp, actiCHamp (Plus), LiveAmp | 연구용. actiCHamp Plus 입력임피던스 ≥1 GΩ, 3색 LED 임피던스 |
| **waveguard touch** | ANT Neuro / eemagine(네덜란드·독일) | Ag/AgCl 코팅 소프트 폴리머, 8/32/64ch, 능동 실딩, 250회 세척 수명 | eego mylab, eego 8, eego sports | CE. 미국·캐나다 연구용 한정. 다기관 비교에서 젤 캡과 유의차 없음 |
| **CGX Quick 센서** | CGX/Cognionics(미국) | 능동 건식·반건식 폴리머, LED 임피던스 | Quick-20r v2 / Quick-32r 내장 | 헤드셋 일체형, 전극만 분리 구매 불가 |

### 3.2 수동 건식(범용 커넥터 — ≥1 GΩ 앰프면 어디든)
| 전극 | 제조사 | 사양 | 가격(공개) | 비고 |
|---|---|---|---|---|
| **Ultracortex 콤 전극** | OpenBCI(미국) | 5 mm 콤형 Ag/AgCl 수동 건식, 헤드셋 3D 프린트 | 헤드셋 USD 499.99~(전극 포함) | Cyton 전용 설계지만 전극 자체는 범용 |
| **건식 Ag/AgCl 컵/핀** | Florida Research Instruments(미국) | 일회·재사용 건식 전극 + 리드 키트 | 15개 USD 89.95, 50개 USD 174.95~184.95(마켓플레이스가) | 저가 실험용 |
| **SoftPulse / SoftPulse Flex** | Datwyler(스위스) | 전도성 엘라스토머 + 피부면 Ag/AgCl 코팅, 형상 맞춤 OEM | 견적 | MCScap 건식 캡, Mentalab 건식 옵션이 이 전극 사용. **자체 헤드밴드 제작 시 1순위 부품** |
| MCScap dry / SmartBCI dry | MCS·Mitsar(러시아) | SoftPulse 기반 건식 캡 | 캡 약 6k EUR~ | 제재·AS 리스크 |
| BrainBit Flex | BrainBit | 4ch 건식 | 소비자 | 참고 |

### 3.3 하이브리드·반건식
| 전극 | 비고 |
|---|---|
| **Unicorn Hybrid**(g.tec) | 건식 기본, 소량 젤 추가 시 품질 향상. 소모품 취급 |
| **OpenBCI Gelfree 캡** | 반건식, AC 임피던스 <2.5 kΩ·cm²(10 Hz), Ag/AgCl 라벨 전극 |
| Emotiv EPOC X | 식염수 리필 센서, 14ch, USD 999. 연구·BCI용 |

## 4. 앰프 옵션

### 4.1 의료기기 등급
| 앰프 | 채널/분해능 | 입력임피던스 | 잡음 | 트리거 | 건식 전극 | 규제 | 비고 |
|---|---|---|---|---|---|---|---|
| **g.tec g.USBamp** | 16ch, 24-bit, 최대 38.4 kHz | >1000 GΩ ∥ 220 pF | <0.4 µVrms(1~30 Hz) | 디지털 입력 내장(수량은 매뉴얼 확인), g.TRIGbox 연동 | 모든 g.tec 능동 전극(g.SAHARA는 g.SAHARAbox 경유) | CE 의료기기, FDA 510(k) K060803 | 유선 레퍼런스 앰프. MATLAB/Simulink·LSL 지원 |
| **g.tec g.Nautilus PRO** | 16/32ch SAHARA, 무선 | 능동 전극 | — | 디지털 트리거 입력 | g.SAHARA 또는 g.LADYbird | CE, FDA 등재(GUDID EBCI5200PRO0/EBCI5201PRO0) | 무선 임상 헤드셋 |
| **g.tec g.HIamp** | 80~256ch | — | — | g.TRIGbox | g.SAHARA 직결 | CE | 고밀도 연구 |
| **ANT eego mylab** | 24-bit, 최대 16,384 Hz | >1 GΩ | — | **8-bit TTL** | waveguard touch(건식)·젤 캡 | CE(미국 연구용) | 능동 실딩 |
| **ANT eego 8** | 8ch | >1 GΩ | — | 2-bit TTL | waveguard touch 완전 호환 | — | 소형 |
| **Brain Products actiCHamp Plus** | 32~160ch | ≥1 GΩ | — | 8-bit 트리거 | 건식·식염수 호환, LED 임피던스 | 연구용 | LSL-actiCHamp 공식 |
| BioSemi ActiveTwo | 능동 전극 | 10¹² Ω ∥ 11 pF(50 Hz 300 MΩ) | — | 갈바닉 절연 37핀 디지털 I/O | 자사 능동 **젤** 전극 전용 | 연구용 | 건식 조합 불가, 참고용 |

### 4.2 연구·저가
| 앰프 | 사양 | 가격 | 트리거 | 앱 연동 | 한계 |
|---|---|---|---|---|---|
| **OpenBCI Cyton (+Daisy)** | ADS1299, 8ch(16ch), 24-bit, 250 Hz 기본(최대 16 kHz SD 기록) | USD 1,249 / 2,499 | 디지털 입력 D11·D12·D13·D17·D18(Digital Read 위젯, 가속도계와 배타) | GUI Networking → LSL(3 스트림) | 트리거가 LSL 스트림에 기본 포함되지 않음 → 포토다이오드 입력 또는 시리얼 마커 필요. 비의료 |
| **g.tec Unicorn Hybrid Black** | 8ch, 24-bit, **250 Hz**, 가속도·자이로 | 비공개(소비자가) | 별도 트리거 박스 미확인 | UnicornLSL / UDP(Windows) | 샘플링 미달, 보증 EU 6개월·기타 30일 |
| **Mentalab Explore+** | 8/16/32ch, 1 kHz, 1 µV 잡음, 12시간 | 비공개 | 소프트웨어 마커(LSL) | explorepy → LSL, 임피던스 명령 | 건식 옵션(Datwyler) 있으나 사용자 평 "습식이 낫다". 비의료 |
| Bitbrain Diadem / Versatile | 12ch 건식 / 8~64ch | 비공개 | — | SDK | 비의료 |

### 4.3 자체 프런트엔드 설계 부품
| 역할 | 부품 | 핵심 사양 | 비고 |
|---|---|---|---|
| **ADC 프런트엔드** | **TI ADS1299 / -4 / -6** | 24-bit, 4/6/8ch, DC 입력임피던스 1 GΩ(리드오프 시 500 MΩ), 바이어스 ±300 pA, 잡음 1 µVpp(70 Hz), CMRR −110 dB, 리드오프 6 nA 전류원(임피던스 측정), GPIO 4(트리거 입력) | 사실상 업계 표준(OpenBCI·HackEEG). 데이지체인으로 32ch |
| **능동 전극 버퍼** | **TI LMP7721** | 입력 바이어스 3 fA(typ, 최대 ±20 fA), 6.5 nV/√Hz, 가드 핀 배치 | 전극 바로 뒤 유니티게인 버퍼. INA116은 NRND(INA121 대체 제안) |
| 저가 버퍼 | OPA376/OPA2376, LMP7702 | pA급 CMOS, 저잡음 | 비용 우선 시 |
| 전극 소재 | Datwyler SoftPulse, 금도금 스프링핀 | Ag/AgCl 코팅 엘라스토머 / 2-와이어 능동 스프링핀(Sensors 2019) | 부트스트랩 2선식으로 케이블 수 절감 |
| 격리·전원 | 의료용 DC/DC, USB 격리 | IEC 60601-1 환자 누설전류 | 임상 필수 |
| 참고 설계 | TI ADS1299EEGFE EVM, 2024 오픈소스 능동 건식 보드(preprint), HackEEG(ADS1299 Arduino 쉴드 8~32ch) | — | — |

## 5. 추천 조합

### 5.1 임상 도입(병원 납품)
**g.USBamp + g.SAHARAbox + g.SAHARA hybrid ×3~5**(Oz 활성, Fz 기준, 접지, 선택 O1/O2) 또는 **g.Nautilus PRO 16ch SAHARA**.
- 근거: 유일하게 "CE 의료기기 앰프 + 능동 건식 전극 + 디지털 트리거 + LSL"을 한 제조사가 모두 제공. 전극 위치가 자유로워 ISCEV Oz 배치 가능.
- 자극기 트리거(본 앱 `Stimulator.present()`의 TTL)를 g.USBamp 디지털 입력에 연결 → LSL 데이터 스트림의 트리거 채널로 수신.
- 주의: SAHARA 건식의 SSVEP 진폭이 작다는 보고 → 평균 횟수 100회 이상, 건식 전용 정상치.

### 5.2 연구·파일럿(정상치 수집, 데모)
**OpenBCI Cyton 8ch + Ultracortex 콤 전극(또는 FRI 건식 핀 + 헤드밴드)**.
- 총 USD 1,800 내외. ADS1299 기반이라 §2 조건 충족.
- 트리거: 패턴 자극 모니터 모서리에 포토다이오드 → D11 디지털 입력(Digital Read), 또는 자극 PC가 LSL 마커 스트림 송출.
- 비의료기기이므로 환자 검사에는 사용 불가.

### 5.3 자체 제품(국제메디언스 브랜드 건식 VEP 헤드밴드)
**ADS1299-4(4ch) + LMP7721 능동 버퍼 + Datwyler SoftPulse 3점(Oz·Fz·접지) 헤드밴드 + USB 격리**.
- 본 앱이 요구하는 것은 µV 샘플 스트림 + 트리거 인덱스(`SampleStream.last_triggers`)뿐이므로 펌웨어는 단순 시리얼 CSV(`serial-csv` 드라이버) 또는 LSL 아웃렛으로 충분.
- 인증: IEC 60601-1 + IEC 80601-2-26 → 식약처 2등급(뇌파계) 경로. 건식 전극 접촉 임피던스 측정값은 IEC 80601-2-26의 임피던스 표시 요구에 맞춰 kΩ~MΩ 로그 스케일로 표시.

## 6. 본 시스템(앱)에서 바뀌어야 할 것
현재 `app/acquisition/hw_streams.py`의 `LSLSampleStream`은
1. **채널 0만** 사용한다(`arr[:, 0]`) → g.tec·OpenBCI·Unicorn은 트리거를 **데이터 스트림의 마지막 채널**로 넣으므로 활성 채널 선택과 트리거 채널 지정이 필요하다.
2. **트리거를 전혀 처리하지 않는다**(`last_triggers` 미설정) → `nidaq` 드라이버처럼 `trig=<채널>;thr=<값>` 옵션으로 상승 에지를 검출하고, 별도 **LSL 마커 스트림**(`type='Markers'`)도 받아 샘플 인덱스로 변환해야 한다.
3. 임피던스 경고가 **5 kΩ 고정**(Live 페이지) → 전극 타입(`wet`/`dry`)별 임계값(건식: 제조사 권고, 예 500 kΩ) 분기.
4. VEP 단계의 기본 평균 횟수 64회를 건식 선택 시 100~128회로 올리는 옵션.

제안 연결 문자열 예: `LIVE_STREAM_DRIVER=lsl`, `STREAM_CONNECTION="name=g.USBamp;ch=1;trig=17;thr=0.5"` 또는 `"name=obci_eeg1;ch=1;markers=VEP_markers"`.

## 7. ERG에는 적용 불가
ERG는 각막·하안검에서 수 µV~수백 µV를 기록하며 안검근 EMG 위에 얹히므로, 머리카락이 없는 하안검에서도 **젤 접착 Ag/AgCl 피부 전극**(LKC Sensor Strip, Ambu Neuroline)이 하한이다. 건식 핀·콤 전극은 안검 피부에 부착할 수 없다. 건식 VEP + 젤 피부 ERG의 혼합 구성이 현실적이다(앱은 채널별 전극 타입을 따로 가질 수 있어야 한다).

## 8. 미확인 사항
- g.USBamp 디지털 입력 수, g.SAHARAbox 가격, Unicorn·Mentalab·eego 가격(모두 견적).
- Unicorn Hybrid Black의 외부 TTL 트리거 지원 여부.
- OpenBCI GUI의 Digital Read 값이 LSL 스트림에 포함되는지(문서상 미확인 → 포토다이오드/마커 방식 권장).
- 제조사 사이트 일부(g.tec 상세 매뉴얼, Mentalab 데이터시트)는 이 세션 네트워크에서 직접 열 수 없어 검색 결과 기준으로 정리함.

## 출처
- TI ADS1299 데이터시트: https://www.ti.com/document-viewer/ADS1299/datasheet/specifications , https://www.ti.com/product/ADS1299
- TI LMP7721: https://www.ti.com/document-viewer/LMP7721/datasheet ; INA116 NRND: https://www.ti.com/product/ko-kr/INA116 ; E2E 토론: https://e2e.ti.com/support/amplifiers-group/amplifiers/f/amplifiers-forum/277116/ina116-ecg-acquisition
- g.USBamp 사양: https://hct.projects.unibz.it/biosignal-amplifiers/ , FDA K060803: https://510k.innolitics.com/device/K060803 , MATLAB 연동: https://in.mathworks.com/products/connections/product_detail/gtec-biosignal-amplifiers.html
- g.SAHARA hybrid·g.SAHARAbox: https://www.gtec.at/product/g-sahara-hybrid/ , https://www.gtec.at/product/gsahara-hybrid-eeg-electrodes/ , g.GAMMAcap: https://www.gtec.at/product/ggammacap-research-eeg-cap/ , g.Nautilus PRO GUDID: https://accessgudid.nlm.nih.gov/devices/EBCI5200PRO0
- Unicorn Hybrid Black: https://www.gtec.at/product/unicorn-hybrid-black/ , LSL: https://www.fieldtriptoolbox.org/development/realtime/unicorn/ , 약관: https://www.gtec.at/terms-and-conditions/
- ANT eego mylab / eego 8 / waveguard touch: https://ant-neuro.com/eegomylab , https://ant-neuro.com/eego-8 , https://www.ant-neuro.com/waveguardtouch
- Brain Products actiCAP Xpress Twist / actiCHamp Plus: https://www.brainproducts.com/solutions/acticap-xpress-twist , https://pressrelease.brainproducts.com/actichamp_plus/ , https://github.com/brain-products/LSL-actiCHamp , 제3자 설치 사양: https://biocrfgz.hkust-gz.edu.cn/?p=2684
- BioSemi ActiveTwo 사양: https://biosemi.com/activetwo_full_specs.htm , https://biosemi.com/faq/compare_specifications.htm
- OpenBCI Cyton·Ultracortex·LSL·외부 트리거: https://shop.openbci.com/products/cyton-biosensing-board-8-channel , https://shop.openbci.com/products/cyton-daisy-biosensing-boards-16-channel , https://shop.openbci.com/products/ultracortex-mark-iv , https://docs.openbci.com/Software/CompatibleThirdPartySoftware/LSL/ , https://docs.openbci.com/Cyton/CytonExternal/ , Gelfree: https://docs.openbci.com/AddOns/Headwear/GelfreeElectrodeCap/
- Mentalab Explore(+): https://www.pr.com/press-release/860856 , explorepy: https://explorepy.readthedocs.io/en/latest/usage.html
- Datwyler SoftPulse: https://datwyler.com/company/innovation/softpulse/technology/ , MCScap 건식(SoftPulse 사용): https://mks.ru/brochures/download/dry-electrodes-27082024 , Mentalab·Datwyler: https://wt-obk.wearable-technologies.com/?p=40241
- Florida Research Instruments 건식 전극 가격: https://www.ebay.de/itm/191640296667 , https://www.ebay.de/itm/201301775957
- 건식 전극·앰프 리뷰(IEC 80601-2-26 기준): https://hdl.handle.net/11250/2733137 ; 능동 전극 리뷰 Xu 2017: https://pmc.ncbi.nlm.nih.gov/articles/PMC4168519/ ; A*STAR 건식 임피던스: https://oar.a-star.edu.sg/communities-collections/articles/20140 ; 2선식 능동 스프링핀: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6833060/ ; 2025 능동 건식 임상 EEG: https://arxiv.org/pdf/2503.23338 ; HackEEG: https://www.crowdsupply.com/starcat/hackeeg/updates/hackeeg-and-openbci
