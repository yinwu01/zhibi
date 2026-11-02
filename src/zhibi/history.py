"""A local event graph of supplied snapshots; never a cross-account identity graph."""
from .models import InputError, exact, profile, timestamp, validate_observations


def timeline(snapshots, same_context=False):
    if not 2 <= len(snapshots) <= 20:
        raise InputError("时间线需要 2 到 20 份本地快照。")
    runs = []
    for data in snapshots:
        is_sample = data.get("sample") is True
        keys = ({"schema_version", "sample", "profile", "observations", "evaluated_at"} if is_sample
                else {"profile", "observations", "generated_at"})
        exact(data, keys, keys)
        if is_sample and data["schema_version"] != "1":
            raise InputError("合成快照版本无效。")
        at = timestamp(data["evaluated_at"] if is_sample else data["generated_at"])
        context = profile(data["profile"])
        items = validate_observations(data["observations"])
        runs.append((at, context, {i["check_id"]: i for i in items}, is_sample))
    runs.sort(key=lambda x: x[0])
    if len({r[0] for r in runs}) != len(runs):
        raise InputError("时间线快照的执行时间必须不同。")
    if len({r[3] for r in runs}) != 1:
        raise InputError("合成示例与真实快照不能合并成同一时间线。")
    nodes, edges, changes = [], [], []
    for n, (at, context, items, sample) in enumerate(runs):
        rid = "run:" + str(n + 1)
        nodes.append({"id": rid, "kind": "run", "at": at.isoformat(), "sample": sample})
        for cid, item in items.items():
            oid = rid + "/" + cid
            nodes.append({"id": oid, "kind": "observation", "check_id": cid,
                          "at": item["at"], "status": item["status"]})
            edges.append({"from": oid, "to": rid, "relation": "recorded_in"})
        if n:
            prior = runs[n - 1]
            previous = "run:" + str(n)
            edges.append({"from": previous, "to": rid, "relation": "precedes"})
            context_matches = context == prior[1]
            comparison = "user_declared_same_context" if same_context and context_matches else "not_established"
            details = []
            if comparison != "not_established":
                for cid in sorted(items.keys() | prior[2].keys()):
                    left, right = prior[2].get(cid), items.get(cid)
                    if left is None or right is None:
                        kind = "coverage_changed"
                    elif left["status"] != right["status"]:
                        kind = "measurement_status_changed"
                    elif left["status"] == "ok" and left["facts"] != right["facts"]:
                        kind = "observed_values_changed"
                    else:
                        continue
                    details.append({"check_id": cid, "change": kind})
            changes.append({"before": previous, "after": rid, "context_matches": context_matches,
                            "comparability": comparison, "changes": details})
    return {"format": "zhibi-local-timeline-1", "sample": runs[0][3], "nodes": nodes, "edges": edges,
            "comparisons": changes,
            "notice": "仅组织提供的本地事件；不输出 IP 等原始事实，不合并身份。时间与观测状态仍属私人信息。"
                      "同上下文是用户声明，变更不代表因果或风险变化；没有平台全局账号图。"}
