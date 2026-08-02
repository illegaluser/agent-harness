#!/usr/bin/env python3
"""
EN: Read-only aggregator over recorded sub-agent transcripts. It never writes
    any file. Data source (confirmed by inspecting real files, see docs):
    ~/.claude/projects/<project-slug>/<session_id>/subagents/agent-<agentId>.jsonl
    with a sibling agent-<agentId>.meta.json holding {agentType, description,
    spawnDepth, toolUseId}. Each .jsonl line is one message record; assistant
    records carry a `usage` object (input_tokens, output_tokens,
    cache_creation_input_tokens, cache_read_input_tokens) and every record
    (user or assistant) carries an ISO-8601 `timestamp`.
KO: 기록된 서브에이전트 트랜스크립트를 읽기만 하는 집계기. 어떤 파일도 쓰지 않는다.
    데이터 위치(실제 파일을 읽어 확인):
    ~/.claude/projects/<project-slug>/<session_id>/subagents/agent-<agentId>.jsonl
    옆에 agent-<agentId>.meta.json 이 {agentType, description, spawnDepth,
    toolUseId} 를 담는다. .jsonl 각 줄은 메시지 레코드 하나이고, assistant
    레코드에는 `usage` 객체(input_tokens·output_tokens·
    cache_creation_input_tokens·cache_read_input_tokens)가, 모든 레코드
    (user/assistant 공통)에는 ISO-8601 `timestamp` 가 있다.
"""
import argparse
import glob
import json
import os
import statistics
from datetime import datetime


def parse_ts(ts):
    # EN/KO: Zulu-suffixed ISO 8601 -> aware datetime.
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")


def load_run(jsonl_path):
    """
    EN: Parse one agent-<id>.jsonl. Returns (metrics-dict or None, skipped_lines).
        A run with zero usable usage records yields None (excluded from stats).
    KO: agent-<id>.jsonl 하나를 파싱한다. (지표 dict 또는 None, 건너뛴 줄 수) 반환.
        usage 레코드가 하나도 없으면 None(집계에서 제외).
    """
    skipped = 0
    ctx_peak = 0
    new_tok = 0
    out_tok = 0
    tool_calls = 0
    timestamps = []

    with open(jsonl_path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                skipped += 1
                continue

            ts = record.get("timestamp")
            if ts:
                try:
                    timestamps.append(parse_ts(ts))
                except ValueError:
                    pass

            message = record.get("message")
            if not isinstance(message, dict):
                continue

            usage = message.get("usage")
            if isinstance(usage, dict):
                inp = usage.get("input_tokens", 0) or 0
                cache_read = usage.get("cache_read_input_tokens", 0) or 0
                cache_create = usage.get("cache_creation_input_tokens", 0) or 0
                out = usage.get("output_tokens", 0) or 0
                ctx_peak = max(ctx_peak, inp + cache_read + cache_create)
                new_tok += inp + cache_create
                out_tok += out

            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls += 1

    if new_tok == 0 and out_tok == 0 and ctx_peak == 0:
        return None, skipped

    wall_s = 0.0
    if len(timestamps) >= 2:
        wall_s = (max(timestamps) - min(timestamps)).total_seconds()

    return {
        "ctx_peak": ctx_peak,
        "new_tok": new_tok,
        "out_tok": out_tok,
        "tool_calls": tool_calls,
        "wall_s": wall_s,
    }, skipped


def collect(session_id=None):
    """
    EN: Walk the corpus (or one session) and group run metrics by agentType.
    KO: 전체 코퍼스(또는 세션 하나)를 순회해 agentType 별로 런 지표를 묶는다.
    """
    root = os.path.expanduser("~/.claude/projects")
    if session_id:
        pattern = os.path.join(root, "*", session_id, "subagents", "agent-*.meta.json")
    else:
        pattern = os.path.join(root, "*", "*", "subagents", "agent-*.meta.json")

    by_type = {}
    total_skipped = 0

    for meta_path in glob.glob(pattern):
        try:
            with open(meta_path, "r") as fh:
                meta = json.load(fh)
        except (ValueError, TypeError, OSError):
            total_skipped += 1
            continue

        agent_type = meta.get("agentType", "unknown")
        jsonl_path = meta_path[: -len(".meta.json")] + ".jsonl"
        if not os.path.isfile(jsonl_path):
            continue

        metrics, skipped = load_run(jsonl_path)
        total_skipped += skipped
        if metrics is None:
            continue

        by_type.setdefault(agent_type, []).append(metrics)

    return by_type, total_skipped


def pctl(values, p):
    """EN/KO: nearest-rank percentile, no extra deps beyond statistics/sorted list."""
    if not values:
        return 0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(p / 100.0 * (len(ordered) - 1)))))
    return ordered[k]


def summarize(by_type):
    metrics_names = ["ctx_peak", "new_tok", "out_tok", "tool_calls", "wall_s"]
    summary = {}
    for agent_type, runs in by_type.items():
        n = len(runs)
        row = {"n": n}
        for m in metrics_names:
            values = [r[m] for r in runs]
            row[m] = {
                "median": statistics.median(values),
                "p90": pctl(values, 90),
                "p99": pctl(values, 99),
                "max": max(values),
            }
        summary[agent_type] = row
    return summary


def print_table(summary, total_skipped):
    metrics_names = ["ctx_peak", "new_tok", "out_tok", "tool_calls", "wall_s"]
    total_n = sum(row["n"] for row in summary.values())
    print(f"total n = {total_n}")
    print()
    for agent_type in sorted(summary.keys(), key=lambda k: -summary[k]["n"]):
        row = summary[agent_type]
        print(f"== {agent_type} (n={row['n']}) ==")
        header = f"{'metric':<12}{'median':>12}{'p90':>12}{'p99':>12}{'max':>12}"
        print(header)
        for m in metrics_names:
            stats = row[m]
            print(
                f"{m:<12}"
                f"{stats['median']:>12,.0f}"
                f"{stats['p90']:>12,.0f}"
                f"{stats['p99']:>12,.0f}"
                f"{stats['max']:>12,.0f}"
            )
        print()
    print(f"skipped: {total_skipped}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default=None, help="session id to restrict to")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args()

    by_type, total_skipped = collect(args.session)
    summary = summarize(by_type)

    if args.json:
        print(json.dumps({"summary": summary, "skipped": total_skipped}, indent=2))
    else:
        print_table(summary, total_skipped)


if __name__ == "__main__":
    main()
