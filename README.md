# PHP 7.2 Bionic Security Backport

Ubuntu 18.04의 특정 PHP 7.2 소스에 **CVE-2026-109618 / CVE-2026-109619**
최소 완화를 적용하고, 기존 설정과 확장 ABI를 유지하며 로컬 패키지를 만드는
소스·도구 모음입니다. PHP 공식 7.4 수정과 Shivam Mathur의 7.2 이식을
기존 Ubuntu vendor patch 위에 맞췄습니다.

**공식 PHP/Ubuntu 보안 업데이트나 PHP 7.2 지원 재개를 뜻하지 않습니다.**
이 패치는 해당 결함의 임시 대응입니다. 장기적으로 지원되는 런타임으로
이전하고 패키지·확장·OS 보안 업데이트를 계속 관리해야 합니다.

## 지원하는 기준선

| 항목 | 값 |
|---|---|
| OS / 아키텍처 | Ubuntu 18.04 Bionic / amd64 |
| 원본 패키지 | `7.2.24-0ubuntu0.18.04.17` |
| 엔진 / 확장 ABI | PHP 7.2.24 / NTS / API20170718 |
| 소스 | orig/debian 아카이브 + Ubuntu vendor patch 95개 |
| 보안 패치 | C/헤더 16파일; 파일별 기준/결과 SHA-256 고정 |
| 로컬 빌드 버전 | `7.2.24-0ubuntu0.18.04.17+local1+rebuild<UTC>` |
| 로컬 엔진 표식 | `7.2.24-0ubuntu0.18.04.17-local1` |

배포판 이름이나 머신 이미지 이름이 같은 것만으로 호환된다고 판단하지
않습니다. [환경·이미지 확인 기준](ENVIRONMENT.md)을 먼저 읽고 실제 패키지와
실행 파일 해시를 확인하세요. PPA, 다른 배포판 개정, ARM, ZTS에는 이 패치를
그대로 적용하지 않습니다.

## 빠른 시작: 읽기 전용 확인

```bash
git clone https://github.com/tom221101/php72-bionic-backport.git
cd php72-bionic-backport
python3 tools/verify.py baseline
```

`baseline`은 대상 서버의 OS·아키텍처·원본 패키지 4개와 실행 파일 3개의
해시를 검사합니다. 설치·재시작·앱 실행·DB 연결은 하지 않습니다. 다른 기준선이면
검사를 우회하지 말고 해당 소스와 패키지에 맞는 별도 이식을 검토하세요.

이 저장소는 소스 빌드용입니다. 릴리즈의 `.deb` 3개는 **수정 전 Ubuntu 원본**으로,
빌드 시 패키지 구조와 호환성을 비교하기 위한 입력입니다. 보안 수정 패키지로
설치하지 마세요. 수정 패키지는 아래 빌드로 생성합니다.

## 격리 환경에서 빌드

서비스와 분리된 Bionic amd64 빌드 환경에 Python 3.6+, GCC/make, autoconf,
bison/re2c, pkg-config, dpkg-dev/fakeroot, PHP 7.2 CLI와 필요한 개발 헤더를
준비합니다. 상세 의존성과 이미지 조건은 [ENVIRONMENT.md](ENVIRONMENT.md)에
있습니다. 도구가 없다고 기존 서비스 서버에 자동 설치하지 않습니다.

릴리즈 입력은 인증 없이 다운로드할 수 있습니다. GitHub CLI가 있다면:

```bash
gh release download v1.0.0 --repo tom221101/php72-bionic-backport --dir downloads
(cd downloads && sha256sum --check SHA256SUMS)
python3 tools/prepare.py --downloads downloads --work .work/build-001
python3 tools/build.py --work .work/build-001 --original-packages downloads
```

CLI 없이도 [릴리즈 페이지](https://github.com/tom221101/php72-bionic-backport/releases/tag/v1.0.0)에서
입력 5개와 체크섬을 받을 수 있습니다. `prepare.py`는 아카이브·vendor series·
C 패치·16개 결과 파일을 검사하고, **새 작업 디렉터리**에만 소스를 준비합니다.
`build.py`는 VM 재생성, 3개 SAPI 구성, 빌드, 패키징을 수행합니다.
기존 소스를 덮어쓰거나 `make install`을 실행하지 않습니다.

먼저 구성만 확인하려면 `build.py`에 `--configure-only`를 추가하세요.
구성 단계는 VM 생성과 기본 설정 경로 `/etc`를, 패키징 단계는 원본 export
심볼·내장 모듈, 동적 라이브러리, RELRO/BIND_NOW를 검사합니다.
구성만 실행한 결과를 빌드 통과로 판단하지 않습니다.

## 생성한 패키지 검증

```bash
python3 tools/verify.py --manifest .work/build-001/manifest.json packages .work/build-001
python3 tools/verify.py --manifest .work/build-001/manifest.json smoke \
  --php .work/build-001/package-cli/usr/bin/php7.2
```

반드시 **빌드 결과의 manifest**를 사용합니다. 루트 manifest의
`patchedPackages`는 비어 있는 빌드 템플릿입니다. 이 상태에서는 `packages`,
`smoke`, `installed`가 실패하며 검사 통과로 표시하지 않습니다.

`smoke`는 `-n`과 전용 임시 session 디렉터리로 배열·복사·직렬화·객체·CONCAT·
session 저장/재개 9개 assertion을 확인합니다. 앱/INI bootstrap이나 DB를
사용하지 않습니다. 이 검사만으로 실제 사이트의 확장·업로드·웹 E2E를
통과했다고 판단하지 않습니다.

## Stage에서 적용하고 운영으로 확대

1. 대상·작업 창·설치 및 FPM 재시작 권한을 확인합니다. 기존 INI/pool, 서비스
   설정, 공유 확장, 원본 패키지와 복귀 절차를 별도 보존합니다.
2. 실제 원본과 후보의 모듈·`ldd`·FPM 설정을 비교합니다. `php7.2-common`,
   OPcache 및 기존 공유 확장은 원래 기준선을 유지합니다.
3. 검증한 빌드 결과의 **정확한 CLI/CGI/FPM 세 파일**을 설치합니다.
   패키지 후처리가 서비스를 재시작할 수 있으므로 설치 전에 영향을 확인합니다.
   원본과 수정본을 함께 설치하는 `*.deb` 명령은 사용하지 않습니다.
4. `php-fpm7.2 -t`, `nginx -t` 및 아래 실행 이미지 검사를 수행합니다.

```bash
sudo python3 tools/verify.py --manifest .work/build-001/manifest.json installed
```

5. Stage에서 정상 session 지속·업로드·사용 중인 파서·후속 요청을 확인하고
   전후 설정·모듈·로그를 비교합니다. 공유 FPM에 RCE/OOM/fatal 입력을 넣지 않습니다.
6. 해당 범위를 통과하면 같은 패키지와 manifest로 운영 적용을 배정합니다.
   새 서버에서는 기준선과 실행 이미지 검사를 다시 수행합니다.

`installed`는 root로 FPM master/worker와 PHP 7.2 프로세스를 확인합니다.
디스크 파일만 교체되고 기존 CLI/cron이 구 실행 이미지를 사용하면
`remainingProcesses`와 **exit 2**를 반환합니다. 작업 소유권·중복 처리·데이터
영향을 확인하기 전에는 기존 작업을 종료하거나 재실행하지 않습니다.
nginx와 php7.2-fpm systemd 서비스가 있는 프로필을 기준으로 합니다.

복귀는 서버별로 보존한 원본 패키지·설정과 승인된 재시작 절차를 사용합니다.
취약 원본으로의 복귀는 보안 대응 완료가 아닙니다. 이미 처리한 요청의 데이터
효과까지 패키지 복귀로 되돌릴 수 있다고 가정하지 않습니다.

## 출처와 검증 한계

[UPSTREAM.md](UPSTREAM.md)에 공식 수정·Shivam 이식·Ubuntu 소스의 고정 참조,
14개 파일의 변경 줄 일치 및 VM 2파일의 차이를 설명했습니다.
해시와 빌드 결과는 환경별로 검증해야 하며, 새 로컬 버전의 전체 컴파일 및
대상 애플리케이션 E2E 통과를 이 저장소 게시만으로 보증하지 않습니다.
SHA-256은 무결성 비교이며 vendor 서명을 대신하지 않습니다.

## 라이선스와 기여

이 저장소에서 작성한 Python 도구와 문서는 [MIT](LICENSE)입니다.
PHP/Zend 코드와 패치는 기존 라이선스를 유지합니다. 구성요소별 고지는
[NOTICE.md](NOTICE.md)와 [LICENSES/](LICENSES/)를 확인하세요.

개선 제안에는 OS·아키텍처·패키지 개정, 재현 절차와 정리한 오류를 포함해 주세요.
회사명·서버 주소·이미지 ID·자격 증명·운영 로그·실제 사용자 데이터는 올리지 마세요.
