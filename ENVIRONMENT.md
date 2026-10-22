# 환경·머신 이미지 확인 기준

## 재사용 가능한 프로필

| 구분 | 요구 조건 |
|---|---|
| 배포판 | Ubuntu 18.04 Bionic |
| 아키텍처 | amd64 / x86_64 |
| 원본 패키지 | CLI / CGI / FPM / common 모두 `7.2.24-0ubuntu0.18.04.17` |
| 실행 파일 | `manifest.json`의 원본 CLI / CGI / FPM SHA-256 일치 |
| PHP ABI | NTS / API20170718 |
| 설정 | `/etc/php/7.2/{cli,cgi,fpm}` 및 기존 pool/conf.d 유지 |
| 확장 | 기존 Ubuntu 공유 확장 유지; 원본과 실제 로드 목록 비교 |
| 서비스 검사 | systemd `php7.2-fpm.service`, `nginx.service` |

원본 패키지의 공통 의존성에는 libc6 `>= 2.27`, libssl1.1 `>= 1.1.0`,
libargon2-0, libpcre3, libsodium23, libxml2, zlib1g 등이 있습니다.
FPM은 libsystemd0/libapparmor1, CLI는 libedit2 등의 의존성도 유지합니다.
전체 의존성은 다운로드한 원본의 `dpkg-deb -f <정확한-파일> Depends`로 확인하세요.
여기에 적힌 하한만 맞췄다고 다른 OS에 설치하지 않습니다.

이 저장소는 AMI ID, 사설 이미지 이름, 호스트 주소 또는 운영 서버 목록을
배포하지 않습니다. `ubuntu:18.04` 같은 컨테이너 태그도 PHP 패키지 개정,
systemd/FPM 구성, 공유 확장을 보장하지 않습니다.

## 같은 이미지인지 확인할 때

서버 담당자는 다음을 내부에서 비교합니다.

1. OS ID/버전, CPU 아키텍처, 설치 패키지 개정과 원본 실행 파일 해시
2. CLI/CGI/FPM 구성, NTS/확장 ABI, 공유 확장과 동적 라이브러리
3. INI, FPM pool, nginx 연결 방식, systemd unit/drop-in, 장기 CLI/cron의 소유권
4. 구성 변경·자동 업데이트 여부, 복귀할 원본 패키지와 설정의 존재

```bash
python3 tools/verify.py baseline
```

이 명령은 앞의 고정 OS/패키지/실행 파일 기준을 검사합니다. 이미지 전체나
모든 설정의 동일성까지 증명하지는 않습니다. 그 밖의 비교 결과는 내부에
보관하고 공개 이슈에는 비밀값과 식별자를 제외한 차이만 공유하세요.

패키지 개정이 다른 경우, 이미 다른 보안 패치를 적용한 경우, ZTS/PPA/ARM
환경은 새 기준선입니다. 검사 우회나 `--force-depends`로 맞추지 않습니다.

## 별도 빌드 환경

원본과 같은 Bionic amd64 환경에 다음 도구·헤더를 준비합니다.

- Python 3.6+, PHP 7.2 CLI, GCC/make, autoconf, bison/re2c, pkg-config, patch
- dpkg-dev, fakeroot, binutils, xz 아카이브 지원
- OpenSSL, libxml2, Argon2, PCRE, sodium, zlib, libevent, systemd, libedit 개발 헤더
- systemtap SDT 헤더

Python 3.6+는 문법/API 호환 조건이며 해당 버전의 지원 상태에 대한 권장이
아닙니다. 빌드용 이미지와 의존성도 별도로 관리해야 합니다.
원본 `.deb`를 실행해 내장 모듈을 비교하므로 필요한 런타임 라이브러리도
빌드 환경에 있어야 합니다. VM 생성용 `php7.2 -n`을 사용하며 앱을 로드하지 않습니다.

빌드 도구는 의존성 설치·전역 `make install`·서비스 재시작을 수행하지 않습니다.
생성 패키지는 기준선이 일치하는 Stage에서 먼저 검증하세요.
