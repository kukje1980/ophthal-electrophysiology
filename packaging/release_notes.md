## 안과 전기생리 검사 시스템 (ISCEV ERG / VEP) — 최신판

아래 두 파일 중 하나를 눌러 내려받으세요 (로그인 필요 없음).

| 파일 | 용도 |
|------|------|
| **OphthalElectrophysiology-windows.zip** | Windows PC용. Python 설치 없이 바로 실행 |
| **ophthal-electrophysiology-source.zip** | 소스 코드. Python 3.12 이상이 있는 PC·서버용 |

### Windows 버전 설치·실행
1. 내려받은 zip 파일의 압축을 풉니다 (예: `D:\OEP`). `Program Files` 안은 피하세요 — 데이터가 프로그램 폴더 옆에 저장됩니다.
2. `OphthalElectrophysiology` 폴더 안의 **OphthalElectrophysiology.exe** 를 실행합니다.
3. "Windows의 PC 보호" 창이 뜨면 **추가 정보 → 실행** 을 누릅니다 (서명하지 않은 프로그램이라 나오는 경고입니다).
4. 검은 콘솔 창이 열리고 잠시 후 브라우저에 <http://localhost:8000> 이 열립니다. 콘솔 창을 닫으면 서버가 종료됩니다.
5. 첫 로그인: 아이디 `admin`, 비밀번호 `admin1234`. **로그인 후 바로 비밀번호를 바꾸세요.**

같은 네트워크의 다른 PC에서 쓰려면 그 PC의 브라우저에서 `http://<서버 PC의 IP>:8000` 으로 접속합니다 (Windows 방화벽에서 8000 포트 허용).

데이터베이스(`ophthal_electrophysiology.db`), 사진(`data\photos`), 백업(`backups`), 로그(`logs`)는 모두 exe 가 있는 폴더에 만들어집니다. 새 버전으로 바꿀 때는 이 파일·폴더들을 새 폴더로 옮기면 됩니다.

설정을 바꾸려면 exe 옆에 `settings.env` 파일을 만들고 한 줄에 하나씩 적습니다. 예:

```
PORT=8000
SECRET_KEY=여기에-긴-무작위-문자열
BACKUP_MIRROR_DIR=E:\OEP-backup
```

### 소스 버전 실행
```bash
pip install -r requirements.txt
python run.py
```

### 항상 최신 버전 주소
- Windows: https://github.com/kukje1980/ophthal-electrophysiology/releases/download/latest/OphthalElectrophysiology-windows.zip
- 소스: https://github.com/kukje1980/ophthal-electrophysiology/releases/download/latest/ophthal-electrophysiology-source.zip

변경 내역은 저장소의 `CHANGELOG.md` 를 참고하세요.
