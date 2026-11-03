# 젤 없는(건식·비접촉) VEP용 EEG 전극 제조사 조사 (2026-10)

> 질문: "머리에 젤로 붙이지 않고 신호를 읽는" VEP용 장치를 만드는 회사는 어디인가.
> 범위: (A) 완전 비접촉·용량성 전극, (B) 건식(dry) 전극 헤드셋, (C) 반건식(semi-dry: 식염수·폴리머·전도성 섬유).
> 조사 방법: 제조사 사이트, FDA 510(k)/GUDID, 식약처 보도, 2019~2026 검증 논문 웹 검색. 가격은 공개된 것만 기재.

## 1. 결론 요약

| 구분 | 상용화 수준 | 대표 회사 | VEP 적합성 |
|---|---|---|---|
| **완전 비접촉(용량성, 머리카락 위에서)** | 연구·자동차용 시제품 단계. **임상 VEP 제품 없음** | Freer Logic(미국), QUASAR(미국), Plessey EPIC(영국) | 학술 데모(SSVEP through hair)만 존재. 임상 불가 |
| **건식 전극, 의료기기 허가** | 임상 EEG로 허가·판매 중 | **Zeto**(미국, FDA 2024), **아이메디신 iSyncWave**(한국, 식약처 2021·FDA 2022), **g.tec g.Nautilus PRO + g.SAHARA**(오스트리아, CE·FDA), CGX(미국) | Zeto급 헤드셋으로 P100 VEP가 습식과 동등(p>0.10)이라는 피어리뷰 근거 있음 |
| **건식 전극, 연구용** | 연구용으로 다수 | Wearable Sensing(DSI-24/DSI-VR300), ANT Neuro waveguard touch, Bitbrain Diadem, Neuroelectrics Enobio, MindRove, Neuphony, OpenBCI | SSVEP 분류 정확도 습식과 1 %p 이내. 단, 일부(g.SAHARA)는 진폭이 더 작음 |
| **반건식·소비자/BCI** | 소비자 제품 | Emotiv(식염수·폴리머), Cognixion ONE(SSVEP, FDA Breakthrough 2023), Neurable(헤드폰형 섬유 전극), NextMind(단종) | SSVEP용 BCI 설계. ISCEV 임상 VEP 용도는 아님 |
| **부품 OEM** | 공급 중 | Datwyler SoftPulse(스위스) | 전도성 엘라스토머 + Ag/AgCl 코팅 건식 전극을 OEM 공급 → 자체 헤드셋 제작 시 선택지 |

**핵심 메시지**
1. 사용자가 보신 "비접촉 VEP 전극"은 실제로는 **젤 없는 건식(dry)·반건식 전극**이다. 머리카락 위에서 진짜 비접촉으로 임상 VEP를 기록하는 상용 장치는 2026년 10월 현재 없다.
2. 건식으로 임상 VEP가 가능하다는 가장 강한 근거는 Hinrichs 2018/2020(Sci Rep): 19채널 건식 vs 습식에서 **P100 잠복시·진폭이 통계적으로 동등**, 피검자 다수가 건식 선호. 단 세타·델타 파워가 약간 높았다(저주파 잡음).
3. 건식 전극은 임피던스가 수백 kΩ~MΩ 수준이라 **능동 전극(active) + 고입력임피던스 앰프**가 필수다. ISCEV의 "5 kΩ 이하" 임피던스 규정은 건식에 그대로 적용할 수 없고, 제조사별 기준(LED 임피던스 표시 등)으로 대체된다.
4. 후두부(Oz)는 머리카락이 가장 많은 곳이라 건식 전극이 가장 불리한 부위다. 핀형(g.SAHARA 금합금 핀) 또는 소프트팁(Zeto, waveguard touch 폴리머)으로 두피까지 뚫고 내려가는 설계가 필요하다.
5. 국내 공급 관점 1순위: **아이메디신 iSyncWave**(식약처 허가 국산, FDA K220056). 2순위: **Zeto ONE**(미국 임상 도입 사례 많음, 국내 허가 미확인). 연구·개발 연동 1순위: **g.tec**(LSL 지원 → 본 앱 `lsl` 드라이버에 바로 연결).

## 2. 용어 정리
- **비접촉(non-contact, capacitive)**: 전극이 피부에 닿지 않고 머리카락·직물을 유전체로 하여 용량 결합으로 전위를 읽음. 입력임피던스 10^12 Ω급 능동 회로 필요, 움직임 잡음에 매우 취약.
- **건식(dry)**: 젤 없이 금속 핀·전도성 폴리머·탄소나노튜브 등이 두피에 직접 접촉.
- **반건식(semi-dry)**: 소량의 식염수(Emotiv EPOC X), 흡습 폴리머(Emotiv Insight), 전도성 섬유(MindRove arc, Neurable)로 접촉 저항을 낮춤.

## 3. 회사별 상세

### A. 완전 비접촉(용량성)
| 회사 | 국가 | 제품/기술 | 상태 |
|---|---|---|---|
| **Freer Logic** | 미국(노스캐롤라이나) | 자동차 헤드레스트 비접촉 뇌파 모니터(Changhong과 공동), 특허 US 11,517,240 "Non-contact body and head based monitoring of brain electrical activity" | 2020년 양산 목표였으나 양산 확인 안 됨. B2B(자동차·훈련) |
| **QUASAR** | 미국(샌디에이고) | 용량성 ECG(직물 위)·고임피던스 EEG 센서 원천기술, 2023년 NIH/DoD SBIR 460만 달러, 신생아 EEG 모니터(NIMH 300만 달러) | R&D 회사. 상용 EEG는 스핀오프 Wearable Sensing이 건식으로 판매 |
| **Plessey Semiconductors (EPIC)** | 영국 | 전기전위 집적회로 센서(2011 샘플). 의복 위 ECG, 자동차 시트 | ECG·자동차 중심. EEG 제품 없음 |
| 학술 | UCSD(Chi·Cauwenberghs 2010~) | 비접촉 센서로 머리카락 위에서 SSVEP 기록 데모(10명) | 논문 수준 |

→ **임상 VEP용 비접촉 제품은 없다.** 지금 조달 대상에서 제외하고 동향 모니터링 대상으로만 둔다.

### B. 건식 전극, 의료기기 허가 보유
| 회사 | 국가 | 제품 | 전극 | 허가 | 비고 |
|---|---|---|---|---|---|
| **Zeto Inc.** | 미국(산타클라라) | **Zeto ONE**(2024-06 FDA 510(k)), 구형 WR19/zEEG | 21개 소프트팁 건식, 10-20 배치, 일회용 전극 세트(ZP-200-67001: Soft Flex 17 + Soft Flat 3) | FDA(병원·가정·구급차·항공 이송) | 2025-01 3,100만 달러 투자. 애리조나·텍사스 병원 도입. 가격 비공개. 19ch 건식 vs 습식 P100 VEP 동등 논문(Hinrichs 2020)의 장비로 알려짐(원문 재확인 권장) |
| **아이메디신(iMediSync)** | 한국 | **iSyncWave** | 19채널 Ag/AgCl 코팅 건식, 헬멧형, 250 Hz/24-bit | 식약처 의료기기 인증(2021-12), FDA 510(k) **K220056**(2022-08, GWQ), CE | 서울대병원·서울아산병원 데이터 수집, 부산대병원 이동검진. 소아 속성 표기. 국산 1순위 후보 |
| **g.tec medical engineering** | 오스트리아 | **g.Nautilus PRO** + **g.SAHARA** 하이브리드(건식/습식) 능동 전극 | 금합금 핀형 건식, 능동 | CE 의료기기, FDA 등재(GUDID EBCI5201PRO0) | 제조사가 SSVEP·c-VEP 용도 명시. 단 비교 연구에서 SSVEP 진폭이 타 시스템보다 작았다는 보고. LSL 지원 → 본 앱 `lsl` 드라이버와 호환 |
| **CGX (a Cognionics company)** | 미국(샌디에이고) | **Quick-20r v2**(21 EEG + 2 ExG), **Quick-32r**(30 EEG + 2 ExG) | 능동 건식·반건식 폴리머, LED 임피던스 표시(Brain Products actiCAP slim 기술) | 의료시장은 CGX 직접, **비의료 연구시장은 Brain Products 독점 판매**(2020~) | Kam 2019(NeuroImage) 건식 vs BioSemi 습식: 습식이 소폭 우세 |

### C. 건식 전극, 연구용
| 회사 | 국가 | 제품 | 특징 |
|---|---|---|---|
| **Wearable Sensing** | 미국(샌디에이고, QUASAR 스핀오프 2013) | **DSI-24**(풀헤드 무선 건식), **DSI-VR300**(7채널, 후두부 중심, **P300/VEP 용도 명시**, VR 헤드셋 결합) | VEP 전용 설계가 있는 유일한 건식 제품. 연구용 |
| **ANT Neuro / eemagine** | 네덜란드/독일(베를린) | **waveguard touch** 8/32/64ch, eego 앰프 | Ag/AgCl 코팅 소프트 폴리머 건식, 능동 실딩. 다기관 비교에서 젤 캡과 유의차 없음. 미국·캐나다 연구용 한정. 250회 사용 수명 |
| **Bitbrain** | 스페인 | **Diadem** 12ch(+GND/REF) | 건식, 256 SPS/24-bit, 8시간 배터리. 비의료 |
| **Neuroelectrics** | 스페인 | **Enobio 8/20/32** 건식 옵션 | 탄소나노튜브(CNT) 기반 건식 전극, 젤 전극과 병용 가능 |
| **MindRove** | 헝가리 | **arc** 6+2ch | 반건식 전도성 섬유. FENS 2024 초록: 8명에서 VEP·P300이 상용 시스템과 비교 가능 |
| **Neuphony** | 인도 | Flex cap 8ch | 건식. 2026 Frontiers 검증(P300·MMN vs BioSemi 64ch) |
| **OpenBCI** | 미국 | Ultracortex Mark IV | 3D 프린트 콤형 건식, 오픈소스. 연구·교육 |

### D. 반건식·소비자/BCI
| 회사 | 제품 | 전극 | 비고 |
|---|---|---|---|
| **Emotiv**(미국·호주) | EPOC X 14ch(USD 999), Insight 5ch | 식염수 리필 / 흡습 폴리머 | SSVEP BCI 연구에 다수 사용. 임상 아님 |
| **Cognixion**(미국) | **ONE Axon** | 건식 EEG + AR 디스플레이, **SSVEP(시각 고정) 기반 의사소통** | 2023-05 FDA Breakthrough Device 지정, ALS 임상시험 진행. 510(k) 미확인 |
| **Neurable**(미국) | MW75 Neuro / Neurable One(헤드폰) | 이어패드 내 12 포인트 섬유 건식 | 소비자용. 2025 Series A 3,500만 달러 |
| **NextMind**(프랑스→Snap) | Dev Kit(후두부 건식, SSVEP 디코딩) | 핀형 건식 | 2022 Snap 인수 후 **단종** |
| **Zeto·Muse·BrainBit** 등 | 헤드밴드 | 건식 | 명상·수면 중심 |

### E. 부품(OEM) 공급
- **Datwyler SoftPulse**(스위스): 전도성 엘라스토머 + 피부면 Ag/AgCl 코팅 건식 전극을 형상 맞춤 OEM 공급(SoftPulse Flex). 자체 VEP 헤드밴드(Oz·Fz·접지 3점)를 설계할 경우 가장 현실적인 부품 소스.

### F. 국내 기업
| 회사 | 제품 | 전극 방식 | 상태 |
|---|---|---|---|
| **아이메디신** | iSyncWave | 19ch 건식(Ag/AgCl 코팅) | 식약처·FDA·CE. 국내 유일 허가 건식 뇌파계(19ch 이상) |
| **와이브레인** | MindScan | 미확인(검색상 전극 방식 불명) | 2019 식약처 허가, 누적 처방 30만 건(2025) |
| **룩시드랩스** | LooxidLink(VR 마스크형 뇌파 모듈, 2019) | 건식 | 현재 AI 솔루션으로 전환, 하드웨어 공급 상태 불명 |
| 소소·비웨이브·라이프시맨틱스 | — | — | 검색 결과 없음 |

## 4. VEP 적용 근거(건식 vs 습식)
| 연구 | 장비 | 결과 |
|---|---|---|
| Hinrichs 2020, Sci Rep 10:5218 | 19ch 건식 헤드셋 vs 19ch 습식, 건강 16 + 신경과 환자 16 | **P100 VEP·P3 잠복시·진폭 동등(p>0.10)**, 공간 분포 유사. 세타·델타 파워 소폭↑. 다수 건식 선호 |
| Kam 2019, NeuroImage | 건식(F1) vs BioSemi 습식, 27명 | 전반적 동등하나 습식이 소폭 우세 |
| 2025 벤치마크(n=19) | 건식 시제품 vs 상용 습식 | SSVEP 분류 80.1 % vs 81.1 %, 8/10/12 Hz SNR 유의차 없음 |
| 2026 Sci Rep | 건식 전극 형상 연구 | SSVEP SNR 1.27 dB(건식) vs 1.30 dB(습식 Ag/AgCl) |
| 2018 Sci Rep | 클로형 건식, 12클래스 SSVEP | 1초 자극 평균 정확도 93.2 % |
| g.SAHARA 비교 | g.tec 핀형 | SSVEP 진폭이 타 시스템 대비 작음 |
| 2022 다기관 | 건식 캡 vs 젤 캡 | 채널 신뢰도 81 %, 임피던스↑, 준비시간 62 %↓ |
| MindRove(FENS 2024, 초록) | 반건식 섬유 | VEP·P300 상용 시스템과 비교 가능(8명) |

**해석**
- 분류·잠복시 중심(BCI, P100 잠복시) 지표는 건식으로 충분하다.
- **진폭 절대값**과 저주파 잡음은 습식이 여전히 우세 → ISCEV VEP 2025 기준 임상 보고(진폭 정상치)는 건식 전용 정상치를 따로 두어야 한다(ERG 피부 전극과 같은 논리).
- 19채널 10-20 배치 헤드셋(iSyncWave, Zeto WR19)은 **Oz 위치가 없다**(O1·O2만). ISCEV VEP 표준의 Oz 활성 전극을 쓰려면 21전극 Zeto ONE의 추가 전극 위치, 또는 g.tec·Wearable Sensing처럼 전극 위치를 자유롭게 잡을 수 있는 시스템이 필요하다.

## 5. 추천
| 목적 | 추천 | 이유 |
|---|---|---|
| 국내 병원 임상 VEP(젤 없이) | **아이메디신 iSyncWave** | 식약처·FDA 허가, 국산 서비스, 소아 가능. 단 Oz 부재·VEP 전용 소프트웨어 없음 → 본 앱과 연동 시 트리거 동기 입력 가능 여부 확인 필요 |
| 임상 등급 + Oz 배치 자유 | **g.tec g.Nautilus PRO + g.SAHARA** | CE 의료기기, 능동 건식, 트리거 입력·LSL 지원 → `LIVE_STREAM_DRIVER=lsl`로 즉시 연결 |
| VEP 전용 소형 장비(연구·스크리닝) | **Wearable Sensing DSI-VR300** | 후두부 7채널 VEP/P300 전용 설계, VR 자극 제시와 결합 |
| 미국 임상 레퍼런스 확보 | **Zeto ONE** | FDA 2024, 병원 도입 다수, P100 동등성 논문. 국내 허가·대리점 미확인 |
| 자체 VEP 헤드밴드 개발 | **Datwyler SoftPulse** OEM 전극 + 능동 프런트엔드 | 3점(Oz·Fz·접지) 밴드로 ERG 피부 전극 키트와 패키지화 가능 |
| 완전 비접촉 | 도입 보류 | 상용 임상 제품 없음. Freer Logic·QUASAR 동향만 추적 |

## 6. 본 시스템 연동 메모
- 이미 있는 `lsl` 스트림 드라이버(README 참조)로 g.tec·Wearable Sensing·CGX·Brain Products 계열은 바로 들어온다. Zeto·iSyncWave는 클라우드/전용 소프트웨어 중심이라 원시 데이터 실시간 스트림 API 제공 여부를 공급사에 확인해야 한다.
- 건식 전극용 임피던스 판정: Live 페이지의 "5 kΩ" 고정 경고를 전극 타입별 임계값(건식: 제조사 권고, 보통 수백 kΩ 허용)으로 분기해야 한다.
- 건식은 50/60 Hz·움직임 잡음이 크므로 VEP 평균 횟수를 기본 64회에서 100회 이상으로 올리는 옵션과 아티팩트 거부 임계 하향이 필요하다.

## 7. 미확인 사항
- Zeto ONE·g.tec·iSyncWave의 국내 가격, iSyncWave의 외부 트리거 입력 지원 여부.
- Hinrichs 2020 논문에서 사용한 건식 헤드셋 제조사명(Zeto로 알려져 있으나 이번 검색 스니펫에서는 명시 확인 안 됨).
- 와이브레인 MindScan의 전극 방식.
- 이 세션의 네트워크 정책으로 제조사 사이트(konanmedical, lkc, diagnosys 등)와 PMC 원문은 직접 열 수 없어 검색 결과 기준으로 정리함.

## 출처
- Hinrichs 2020 Sci Rep(건식 vs 습식, P100): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7090045/
- Kam 2019 NeuroImage 요약: https://cris.iucc.ac.il/en/publications/systematic-comparison-between-a-wireless-eeg-system-with-dry-elec/
- Zeto ONE FDA 510(k) 2024: https://www.massdevice.com/fda-clears-zeto-eeg-brain-monitoring/ , https://neurologylive.com/view/fda-clears-zeto-adjustable-one-headset-eeg-brain-monitoring
- Zeto 투자·병원 도입: https://www.massdevice.com/zeto-raises-31m-eeg-brain-monitoring/ , https://hcplive.com/view/fda-greenlights-zetos-dry-electrode-wireless-eeg-headset-for-clinical-use
- Zeto 전극 세트 GUDID: https://revmedconnect.com/device/zeto-inc/zp-200-67001/B675ONEESB1
- 아이메디신 iSyncWave 식약처: https://www.hankyung.com/article/202112304799i , FDA K220056: https://fda.innolitics.com/device/K220056 , https://www.imedisync.com/
- g.tec g.SAHARA: https://www.gtec.at/product/gsahara-hybrid-eeg-electrodes/ , g.Nautilus PRO GUDID: https://accessgudid.nlm.nih.gov/devices/EBCI5201PRO0
- CGX / Brain Products: https://www.cgxsystems.com/quick-20r-v2 , https://cgxsystems.com/quick-32r , https://pressrelease.brainproducts.com/cgx/
- Wearable Sensing: https://wearablesensing.com/dsi-vr300/ , QUASAR 스핀오프: https://www.cbinsights.com/company/wearable-sensing , https://mtec-sc.org/life-sciences/wearable-sensing
- ANT Neuro waveguard touch: https://www.ant-neuro.com/waveguardtouch
- Bitbrain Diadem: https://www.bitbrain.com/equipment/products/diadem
- Neuroelectrics Enobio CNT 건식: https://openresearch.surrey.ac.uk/esploro/outputs/journalArticle/ENOBIO-dry-electrophysiology-electrode-first-human/99512373102346
- MindRove VEP/P300 초록: https://world-wide.org/fens-24/validation-portable-dry-electrode-zwylo5dn
- Neuphony 검증: https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2025.1670860/abstract
- Emotiv: https://www.emotiv.com/epoc-x , https://www.emotiv.com/blog/dry-electrode-eeg-headset-guide
- Cognixion FDA Breakthrough: https://alsnewstoday.com/news/wearable-brain-computer-als-named-fda-breakthrough-device/
- Neurable: https://spectrum.ieee.org/eeg-headphones-neurable-one , NextMind 단종: https://www.theatdb.com/companies/nextmind
- Freer Logic 비접촉: https://autotechinsight.spglobal.com/news/5237889/freer-logic-develops-new-headrest-to-monitor-brainwaves-send-alerts-when-driver-is-drowsy- , 특허: https://patents.google.com/patent/US11517240
- QUASAR 용량성·SBIR: https://www.cbinsights.com/company/quasar-1 ; Plessey EPIC: https://www.saelig.com/supplier/plessey/Non-contact%20ECG%20measurement%20using%20EPIC-article0911312P.pdf
- 비접촉 SSVEP through hair(UCSD): https://www.researchgate.net/publication/51899048_Dry_and_Noncontact_EEG_Sensors_for_Mobile_Brain-Computer_Interfaces
- 건식 SSVEP 연구: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6168577/ , https://www.nature.com/articles/s41598-026-47459-w , https://www.researchgate.net/publication/413683446
- 2025 건식 전극 리뷰: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12389868/
- Datwyler SoftPulse: https://datwyler.com/company/innovation/softpulse/technology/
- 국내: 와이브레인 https://www.bosa.co.kr/news/articleView.html?idxno=2258488 , 룩시드랩스 https://looxidlabs.com/
