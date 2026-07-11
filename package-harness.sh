#!/usr/bin/env bash
# EN: Build-side packager for the multi-agent harness bundle. This repo
#     (agent-harness) *is* the single canonical source now — there is no
#     separate "live" repo location above it, unlike the private source
#     project snapshot this was extracted from. It stages a self-contained
#     "harness-dist-<ts>/" tree — install-harness.sh + base/{agents,
#     settings.harness.json,hooks,docs/harness,templates} — into
#     build-out/<ts>/, ships it as a single zip (zip-only), and writes a
#     sha256 manifest (HARNESS-BUNDLE.md). Every source file is read directly
#     from base/ — there is no drift-detection step because there is nothing
#     left to drift against. Called manually (`bash package-harness.sh`),
#     never by install-harness.sh.
# KO: 멀티 에이전트 하네스 번들의 빌드측 패키저. 이 저장소(agent-harness)가
#     이제 **유일한 정본**이다 — 이 저장소를 추출해 온 원본 비공개 사설
#     프로젝트 스냅샷과 달리, 위에 별도의 "라이브" 저장소 위치가 없다.
#     독립 실행 가능한 "harness-dist-<ts>/" 트리 —
#     install-harness.sh + base/{agents,settings.harness.json,hooks,
#     docs/harness,templates} — 를 build-out/<ts>/ 에 스테이징하고, zip
#     단독으로 묶고, sha256 매니페스트(HARNESS-BUNDLE.md)를 쓴다. 모든 소스
#     파일을 base/ 에서 직접 읽는다 — 대조할 별도의 라이브 사본이 더는
#     없으므로 drift 감지 단계도 없다. 수동 호출 전용
#     (`bash package-harness.sh`), install-harness.sh 가 이 스크립트를
#     부르는 일은 없다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$SCRIPT_DIR/base"

FORMAT="zip"
DRY_RUN=0

log()  { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
package-harness.sh — 하네스 번들 빌더 (harness-dist)

사용법:
  package-harness.sh [--format zip] [--dry-run]

옵션:
  --format zip   번들 포맷 (기본값이자 유일 지원값 — zip 단독, 계획 Q5)
  --dry-run      스테이징·압축 없이 무엇을 만들지만 출력. 산출물 없음
  -h, --help     이 도움말 출력

산출: harness-dist/build-out/<타임스탬프>/harness-dist-<타임스탬프>.zip
      + 같은 디렉토리의 HARNESS-BUNDLE.md (sha256 매니페스트)
USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --format)
        FORMAT="${2:-}"
        [[ -n "$FORMAT" ]] || die "--format requires a value"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        usage
        die "unknown argument: $1"
        ;;
    esac
  done
  [[ "$FORMAT" == "zip" ]] || die "unsupported --format: $FORMAT (only 'zip' is supported — plan Q5)"
}

# EN: Fails loudly (non-zero exit) the moment any file this bundle depends
#     on is missing, before any staging directory is created. Called once
#     per required source path from check_all_sources(), which runs before
#     anything else in main() — a missing source must never produce a
#     partial, silently-incomplete zip.
# KO: 이 번들이 의존하는 파일이 하나라도 없으면 스테이징 디렉터리를 만들기
#     전에 즉시 비정상 종료한다. main() 의 다른 어떤 동작보다 먼저 도는
#     check_all_sources() 에서 필수 소스 경로마다 한 번씩 호출된다 — 소스가
#     빠졌는데 부분적으로 불완전한 zip이 조용히 만들어지는 일은 없다.
require_source() {
  local path="$1" label="$2"
  [[ -e "$path" ]] || die "missing required source ($label): $path"
}

# EN: Verifies every file this bundle needs actually exists on disk — all of
#     it under base/, since this repo is the single source of truth
#     (install-harness.sh, agents/settings/templates/INSTALL.md/GUIDE.md,
#     docs/harness/00..03.md, hooks/*.sh) — before touching the filesystem.
#     This is the fail-loud gate that runs even under --dry-run so a dry run
#     also catches a broken checkout.
# KO: 이 번들이 필요로 하는 모든 파일이 실제로 디스크에 있는지 확인한다 —
#     이 저장소가 유일한 정본이므로 전부 base/ 아래(install-harness.sh,
#     agents/settings/templates/INSTALL.md/GUIDE.md, docs/harness/00..03.md,
#     hooks/*.sh) — 파일시스템을 건드리기 전에 전부 확인한다. --dry-run
#     에서도 실행되는 fail-loud 게이트이며, 드라이런조차 깨진 체크아웃을
#     잡아낸다.
check_all_sources() {
  require_source "$SCRIPT_DIR/install-harness.sh" "installer"
  require_source "$BASE_DIR/INSTALL.md" "base/INSTALL.md"
  require_source "$BASE_DIR/GUIDE.md" "base/GUIDE.md"

  local name
  for name in scout architect maker critic referee; do
    require_source "$BASE_DIR/agents/$name.md" "base/agents/$name.md"
  done

  require_source "$BASE_DIR/settings.harness.json" "base/settings.harness.json"

  local tmpl
  for tmpl in _repo-facts.md.template agent-specialization-stub.md DECISIONS.seed.md \
              VERIFY.md.template CLAUDE.harness-global.md CLAUDE.harness-project.md.template; do
    require_source "$BASE_DIR/templates/$tmpl" "base/templates/$tmpl"
  done

  local docname
  for docname in 00-definition 01-roles 02-orchestration 03-adoption; do
    require_source "$BASE_DIR/docs/harness/$docname.md" "base/docs/harness/$docname.md"
  done

  local hookname
  for hookname in inject-repo-facts lint-gate; do
    require_source "$BASE_DIR/hooks/$hookname.sh" "base/hooks/$hookname.sh"
  done
}

# EN: Copies every source file into the staging tree at $1 (a fresh
#     "harness-dist-<ts>/" directory), re-chmod'ing every .sh to +x to
#     compensate for exec-bit loss some zip toolchains introduce (Q5). Only
#     called from main() after check_all_sources() has already confirmed
#     every source exists and DRY_RUN is off.
# KO: 모든 소스 파일을 $1(새 "harness-dist-<ts>/" 디렉터리)에 복사하고,
#     일부 zip 툴체인의 exec-bit 손실(Q5)을 보완하기 위해 모든 .sh 를
#     +x 로 재-chmod 한다. check_all_sources() 가 모든 소스 존재를 이미
#     확인하고 DRY_RUN 이 꺼져 있을 때만 main() 에서 호출된다.
stage_bundle() {
  local stage="$1"
  mkdir -p "$stage/base/agents" "$stage/base/hooks" "$stage/base/docs/harness" "$stage/base/templates"

  cp "$SCRIPT_DIR/install-harness.sh" "$stage/install-harness.sh"
  chmod +x "$stage/install-harness.sh"
  cp "$BASE_DIR/INSTALL.md" "$stage/INSTALL.md"
  cp "$BASE_DIR/GUIDE.md" "$stage/GUIDE.md"

  local name
  for name in scout architect maker critic referee; do
    cp "$BASE_DIR/agents/$name.md" "$stage/base/agents/$name.md"
  done

  cp "$BASE_DIR/settings.harness.json" "$stage/base/settings.harness.json"

  local tmpl
  for tmpl in _repo-facts.md.template agent-specialization-stub.md DECISIONS.seed.md \
              VERIFY.md.template CLAUDE.harness-global.md CLAUDE.harness-project.md.template; do
    cp "$BASE_DIR/templates/$tmpl" "$stage/base/templates/$tmpl"
  done

  local docname
  for docname in 00-definition 01-roles 02-orchestration 03-adoption; do
    cp "$BASE_DIR/docs/harness/$docname.md" "$stage/base/docs/harness/$docname.md"
  done

  local hookname
  for hookname in inject-repo-facts lint-gate; do
    cp "$BASE_DIR/hooks/$hookname.sh" "$stage/base/hooks/$hookname.sh"
    chmod +x "$stage/base/hooks/$hookname.sh"
  done
}

# EN: Portable sha256 hex digest of a single file — tries sha256sum
#     (Linux/coreutils) first, falls back to `shasum -a 256` (macOS
#     default). Called once per staged file from write_manifest() and once
#     for the finished archive from main(); dies if neither tool exists so
#     a manifest is never silently written without real checksums.
# KO: 파일 하나의 sha256 hex digest 를 이식성 있게 구한다 — sha256sum
#     (Linux/coreutils) 을 먼저 시도하고, 없으면 `shasum -a 256`(macOS
#     기본)으로 폴백한다. write_manifest() 에서 스테이징된 파일마다 한 번,
#     main() 에서 완성된 아카이브에 한 번 호출된다. 둘 다 없으면 즉시
#     실패해 실제 체크섬 없이 매니페스트가 조용히 쓰이는 일을 막는다.
sha256_of() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path" | awk '{print $1}'
  else
    die "neither sha256sum nor shasum found on PATH — cannot write manifest"
  fi
}

# EN: Writes HARNESS-BUNDLE.md next to the finished archive: build
#     timestamp, build commit, build OS, the archive's own size+sha256, and
#     a per-file sha256 manifest of everything inside the staged tree (used
#     by the "sha256 일치" verification step in the plan — a receiver can
#     re-hash the unzipped tree and diff against this table). Called once
#     from main() after make_archive() so the archive's own hash is
#     available to include.
# KO: 완성된 아카이브 옆에 HARNESS-BUNDLE.md 를 쓴다 — 빌드 타임스탬프,
#     빌드 커밋, 빌드 OS, 아카이브 자체의 크기+sha256, 스테이징 트리 안
#     모든 파일의 sha256 매니페스트(계획서의 "sha256 일치" 검증 단계에서
#     받는 쪽이 압축 해제한 트리를 다시 해시해 이 표와 대조하는 데 쓴다).
#     아카이브 자체 해시를 표에 넣어야 하므로 make_archive() 이후
#     main() 에서 한 번 호출된다.
write_manifest() {
  local stage="$1" archive="$2" manifest_path="$3"
  local build_ts build_commit build_os archive_size archive_sha256
  build_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  build_commit="$(cd "$SCRIPT_DIR" && git rev-parse HEAD 2>/dev/null || echo unknown)"
  build_os="$(uname -s)"
  archive_size="$(wc -c < "$archive" | tr -d ' ')"
  archive_sha256="$(sha256_of "$archive")"

  {
    echo "# HARNESS-BUNDLE.md"
    echo ""
    echo "빌드 타임스탬프(UTC): $build_ts"
    echo "빌드 커밋: $build_commit"
    echo "빌드 OS: $build_os"
    echo "아카이브: $(basename "$archive")"
    echo "아카이브 크기(bytes): $archive_size"
    echo "아카이브 sha256: $archive_sha256"
    echo ""
    echo "## 파일 매니페스트 (스테이징 트리 기준, sha256)"
    echo ""
    echo "| 경로 | 크기(bytes) | sha256 |"
    echo "| --- | --- | --- |"
    while IFS= read -r f; do
      local rel size digest
      rel="${f#"$stage"/}"
      size="$(wc -c < "$f" | tr -d ' ')"
      digest="$(sha256_of "$f")"
      echo "| $rel | $size | $digest |"
    done < <(find "$stage" -type f | sort)
  } > "$manifest_path"
}

# EN: Produces the single supported archive format (Q5: zip-only) from the
#     staged "harness-dist-<ts>/" directory, choosing the tool that
#     preserves POSIX exec bits best on the current OS: `ditto -ck
#     --keepParent` on macOS (Darwin), `zip -qr` elsewhere. Dies on an
#     unrecognized OS with neither tool rather than silently falling back to
#     something that might drop exec bits.
# KO: 스테이징된 "harness-dist-<ts>/" 디렉터리에서 유일 지원 포맷(Q5:
#     zip 단독)을 만든다 — 현재 OS에서 POSIX exec bit 를 가장 잘 보존하는
#     도구를 고른다: macOS(Darwin)는 `ditto -ck --keepParent`, 그 외는
#     `zip -qr`. 인식 못 하는 OS 에 두 도구 다 없으면, exec bit 를 잃을 수
#     있는 다른 수단으로 조용히 폴백하는 대신 즉시 실패한다.
make_archive() {
  local out_dir="$1" stage_name="$2" archive="$3"
  case "$(uname -s)" in
    Darwin)
      command -v ditto >/dev/null 2>&1 || die "ditto not found (expected on macOS)"
      # --norsrc --noextattr --noacl stop ditto from writing AppleDouble
      # "._*" resource-fork/xattr/ACL sidecar entries into the archive —
      # this repo's staged files never carry real resource forks, so those
      # sidecars would be pure noise for a receiver on any other OS
      # (plain COPYFILE_DISABLE=1 was tried first and did not suppress them
      # for `ditto -c -k`; these explicit flags do).
      ditto --norsrc --noextattr --noacl -ck --keepParent "$out_dir/$stage_name" "$archive"
      ;;
    *)
      command -v zip >/dev/null 2>&1 || die "zip not found on PATH — required to build the bundle on this OS"
      (cd "$out_dir" && zip -qr "$(basename "$archive")" "$stage_name")
      ;;
  esac
}

main() {
  parse_args "$@"
  check_all_sources

  local ts stage_name out_dir stage archive manifest
  ts="$(date +%Y%m%dT%H%M%S)"
  stage_name="harness-dist-$ts"
  out_dir="$SCRIPT_DIR/build-out/$ts"
  stage="$out_dir/$stage_name"
  archive="$out_dir/$stage_name.zip"
  manifest="$out_dir/HARNESS-BUNDLE.md"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "WOULD_CREATE $stage"
    log "WOULD_CREATE $archive"
    log "WOULD_CREATE $manifest"
    log "(dry-run: all required sources verified present, nothing written)"
    exit 0
  fi

  mkdir -p "$out_dir"
  stage_bundle "$stage"
  make_archive "$out_dir" "$stage_name" "$archive"
  write_manifest "$stage" "$archive" "$manifest"

  log "== package-harness.sh done =="
  log "bundle:   $archive"
  log "manifest: $manifest"
}

main "$@"
