"""Static viewer for the DeepSeek-V4-Pro hindsight relabel of the precheck's all-failed groups.

Reads results/precheck/episodes.jsonl.gz (trajectories) and results/precheck/llm_relabel.jsonl (one LLM relabel per failed
episode), writes <out_dir>/index.html, <out_dir>/data/index.json and one <out_dir>/data/group_<id>.json per group.
Per group it also simulates two anchor rules: LfH's uniformly chosen failed episode, and a uniformly chosen episode
among those whose relabel was accepted; the anchor's goal rescores all 8 episodes (GRPO advantages shown).
"""
import argparse
import collections
import gzip
import json
import os
import random
import statistics

from llm_relabel import executed_action

TASK_TYPES = ["pick_and_place_simple", "look_at_obj_in_light", "pick_clean_then_place_in_recep",
              "pick_heat_then_place_in_recep", "pick_cool_then_place_in_recep", "pick_two_obj_and_place"]


def grpo(rewards):
    mean = statistics.mean(rewards)
    std = statistics.stdev(rewards)
    return [round((r - mean) / (std + 1e-6), 3) for r in rewards]


def anchor_result(rows, candidates, rng):
    if not candidates:
        return None
    anchor = rng.choice(candidates)
    row = rows[anchor]
    if row["status"] != "accepted":
        return {"anchor": anchor, "goal": None, "status": row["status"]}
    rewards = [float(x) for x in row["rescored"]]
    return {"anchor": anchor, "goal": row["goal"], "instruction": row["llm"].get("instruction"), "status": "accepted",
            "rewards": rewards, "advantages": grpo(rewards) if 0 < sum(rewards) < len(rewards) else [0.0] * len(rewards)}


def read_jsonl(path):
    """Rows of a jsonl file; a half-written last line (file still being written) is skipped."""
    rows = []
    for line in open(path):
        if line.endswith("\n"):
            rows.append(json.loads(line))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", default="results/precheck/episodes.jsonl.gz")
    parser.add_argument("--relabels", default="results/precheck/llm_relabel_prompt_v2.jsonl")
    parser.add_argument("--compare_relabels", default="results/precheck/llm_relabel_prompt_v1.jsonl", help="earlier prompt version, shown for comparison")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    episodes = collections.defaultdict(list)
    for line in gzip.open(args.episodes, "rt"):
        episode = json.loads(line)
        episodes[episode["group"]].append(episode)
    relabels = collections.defaultdict(dict)
    for row in read_jsonl(args.relabels):
        relabels[row["group"]][row["episode_index"]] = row
    compare = {}
    if args.compare_relabels and os.path.exists(args.compare_relabels):
        for row in read_jsonl(args.compare_relabels):
            compare[(row["group"], row["episode_index"])] = row
    compare_counts = collections.Counter()

    os.makedirs(os.path.join(args.out_dir, "data"), exist_ok=True)
    index_rows, status_counts, status_by_type = [], collections.Counter(), collections.defaultdict(collections.Counter)
    coverage = collections.Counter()
    tokens = collections.Counter()
    for group_id in sorted(relabels):
        rows = relabels[group_id]
        if len(rows) != len(episodes[group_id]):
            continue                                    # group not fully relabeled yet
        group_episodes = episodes[group_id]
        ordered = [rows[i] for i in range(len(group_episodes))]
        for i, row in enumerate(ordered):
            if (group_id, i) in compare:
                compare_counts[compare[(group_id, i)]["status"]] += 1
            status_counts[row["status"]] += 1
            status_by_type[row["task_type"]][row["status"]] += 1
            tokens["prompt"] += row["usage"].get("prompt_tokens", 0)
            tokens["completion"] += row["usage"].get("completion_tokens", 0)
        rng = random.Random(f"{args.seed}:{group_id}")
        uniform = anchor_result(ordered, list(range(len(ordered))), rng)
        accepted_only = anchor_result(ordered, [i for i, r in enumerate(ordered) if r["status"] == "accepted"], rng)
        coverage["groups"] += 1
        coverage["uniform_relabeled"] += bool(uniform and uniform["goal"])
        coverage["accepted_only_relabeled"] += bool(accepted_only)
        for name, result in (("uniform", uniform), ("accepted_only", accepted_only)):
            if result and result["goal"]:
                coverage[f"{name}_mixed"] += 0 < sum(result["rewards"]) < len(result["rewards"])
        group = {
            "group": group_id, "task": group_episodes[0]["task"], "task_type": group_episodes[0]["task_type"],
            "task_description": group_episodes[0]["task_description"], "uniform_anchor": uniform, "accepted_anchor": accepted_only,
            "episodes": [{
                "index": i, "steps": e["steps"], "end_mode": e["end_mode"], "full": e["full"], "half": e["half"],
                "holding_at_end": e["holding_at_end"], "state_goals": r["state_goals"], "status": r["status"], "goal": r["goal"],
                "llm": r["llm"], "error": r["error"], "rescored": r["rescored"],
                "compare_status": compare.get((group_id, i), {}).get("status"), "compare_llm": compare.get((group_id, i), {}).get("llm"),
                "trajectory": [{"action": executed_action(t["response"]), "valid": t["action_valid"], "feedback": t["feedback"],
                                "response": t["response"]} for t in e["trajectory"]],
            } for i, (e, r) in enumerate(zip(group_episodes, ordered))],
        }
        json.dump(group, open(os.path.join(args.out_dir, "data", f"group_{group_id}.json"), "w"))
        index_rows.append({"group": group_id, "task_type": group["task_type"], "task_description": group["task_description"],
                           "statuses": [r["status"] for r in ordered], "accepted_goals": sorted({" / ".join(r["goal"]) for r in ordered if r["status"] == "accepted"}),
                           "uniform_goal": uniform["instruction"] if uniform and uniform["goal"] else None,
                           "accepted_goal": accepted_only["instruction"] if accepted_only else None,
                           "accepted_rewards": accepted_only["rewards"] if accepted_only else None})
    version_of = lambda path: os.path.basename(path).rsplit("_", 1)[-1].split(".")[0] if path else ""
    summary = {"status_counts": dict(status_counts), "compare_status_counts": dict(compare_counts),
               "version": version_of(args.relabels), "compare_version": version_of(args.compare_relabels) if compare else "", "status_by_type": {t: dict(status_by_type[t]) for t in TASK_TYPES},
               "coverage": dict(coverage), "tokens": dict(tokens), "model": "DeepSeek-V4-Pro (azure/azure/DeepSeek-V4-Pro)"}
    json.dump({"summary": summary, "groups": index_rows}, open(os.path.join(args.out_dir, "data", "index.json"), "w"))
    with open(os.path.join(args.out_dir, "index.html"), "w") as page:
        page.write(PAGE)
    print(json.dumps(summary, indent=1))


PAGE = r"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>ALFWorld hindsight relabel (DeepSeek-V4-Pro)</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;margin:20px;color:#222;max-width:1200px}
h1{font-size:20px}h2{font-size:16px;margin-top:24px}
table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ddd;padding:3px 7px;text-align:left;vertical-align:top}
.badge{display:inline-block;padding:1px 6px;border-radius:8px;font-size:12px;color:#fff}
.accepted{background:#2e7d32}.rejected{background:#c62828}.none{background:#777}.malformed{background:#ef6c00}.error{background:#6a1b9a}
.group{border:1px solid #ccc;border-radius:6px;margin:8px 0;padding:8px}
.group summary{cursor:pointer}.muted{color:#777}.ok{color:#2e7d32;font-weight:bold}.no{color:#bbb}
.traj td{font-size:12px}.ev{background:#fff7d6}pre{white-space:pre-wrap;margin:0;font-size:12px}
.filters label{margin-right:12px}
</style></head><body>
<h1>ALFWorld hindsight relabel：DeepSeek-V4-Pro 改写全失败组的失败轨迹</h1>
<p class="muted">数据：预检（未训练的 Qwen2.5-1.5B-Instruct，训练采样设置）里 8 局全失败的组。每局由 DeepSeek-V4-Pro 读轨迹，给出"实际完成了什么"（ALFWorld 任务模板）；
用环境状态检查器核对：<span class="badge accepted">accepted</span> 状态里确实发生了，<span class="badge rejected">rejected</span> LLM 声称了但状态里没有（幻觉），
<span class="badge none">none</span> LLM 认为什么都没完成。被接受的目标会给组内 8 局重新打分（✓ = 按新目标算成功），并给出 GRPO advantage。</p>
<div id="summary"></div>
<h2>组列表</h2>
<div class="filters">
<label>任务类型 <select id="type"><option value="">全部</option></select></label>
<label><input type="checkbox" id="onlyAccepted"> 只看有 accepted 的组</label>
<label><input type="checkbox" id="onlyRejected"> 只看有 rejected 的组</label>
</div>
<div id="groups"></div>
<script>
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const badge = s => `<span class="badge ${s}">${s}</span>`;
const pct = (a, b) => b ? (100 * a / b).toFixed(1) + "%" : "—";
let INDEX;
fetch("data/index.json").then(r => r.json()).then(data => { INDEX = data; renderSummary(); renderGroups(); });
function renderSummary() {
  const s = INDEX.summary, c = s.status_counts, total = Object.values(c).reduce((a, b) => a + b, 0), cov = s.coverage;
  let html = `<h2>汇总（${cov.groups} 个全失败组，${total} 局）</h2><table><tr><th>LLM 结论</th><th>局数</th><th>占比</th></tr>`;
  for (const k of ["accepted", "rejected", "none", "malformed", "error"]) html += `<tr><td>${badge(k)}</td><td>${c[k] || 0}</td><td>${pct(c[k] || 0, total)}</td></tr>`;
  html += `</table><p>LLM 声称完成了某个任务的局里，被状态检查器接受的比例：<b>${pct(c.accepted || 0, (c.accepted || 0) + (c.rejected || 0))}</b></p>`;
  const v1 = s.compare_status_counts || {};
  if (Object.keys(v1).length) html += `<p class="muted">对比 ${s.compare_version}（第一次运行：prompt 没有"只有 You move the X to the Y 才算放置""加热/冷却/清洗不算放进去"两条规则，而且给 LLM 的轨迹把大写的 &lt;Action&gt; 错显示成了无效输出）：accepted ${v1.accepted || 0}，rejected ${v1.rejected || 0}，none ${v1.none || 0}，malformed ${v1.malformed || 0}；准确率 ${pct(v1.accepted || 0, (v1.accepted || 0) + (v1.rejected || 0))}。下面每局的"${s.compare_version}"列是它的结论。</p>`;
  html += `<table><tr><th>任务类型</th><th>accepted</th><th>rejected</th><th>none</th><th>malformed</th><th>error</th></tr>`;
  for (const [t, v] of Object.entries(s.status_by_type)) html += `<tr><td>${t}</td>${["accepted","rejected","none","malformed","error"].map(k => `<td>${v[k] || 0}</td>`).join("")}</tr>`;
  html += `</table><h2>锚点规则对比</h2><table><tr><th>规则</th><th>能改写的组</th><th>改写后组内有对有错（有信号）</th></tr>
  <tr><td>LfH：失败局里随机挑锚点</td><td>${cov.uniform_relabeled} / ${cov.groups} (${pct(cov.uniform_relabeled, cov.groups)})</td><td>${cov.uniform_mixed || 0}</td></tr>
  <tr><td>只从 accepted 的局里挑锚点</td><td>${cov.accepted_only_relabeled} / ${cov.groups} (${pct(cov.accepted_only_relabeled, cov.groups)})</td><td>${cov.accepted_only_mixed || 0}</td></tr></table>
  <p class="muted">模型：${esc(s.model)}；token：prompt ${s.tokens.prompt}，completion ${s.tokens.completion}</p>`;
  document.getElementById("summary").innerHTML = html;
  const sel = document.getElementById("type");
  for (const t of Object.keys(s.status_by_type)) sel.innerHTML += `<option>${t}</option>`;
  for (const id of ["type", "onlyAccepted", "onlyRejected"]) document.getElementById(id).onchange = renderGroups;
}
function renderGroups() {
  const type = document.getElementById("type").value, onlyA = document.getElementById("onlyAccepted").checked, onlyR = document.getElementById("onlyRejected").checked;
  const rows = INDEX.groups.filter(g => (!type || g.task_type === type) && (!onlyA || g.statuses.includes("accepted")) && (!onlyR || g.statuses.includes("rejected")));
  document.getElementById("groups").innerHTML = `<p class="muted">${rows.length} 组</p>` + rows.map(g => `
    <details class="group" data-group="${g.group}"><summary><b>组 ${g.group}</b> · ${esc(g.task_type)} · 原任务：<i>${esc(g.task_description)}</i>
      · ${g.statuses.map(badge).join(" ")}<br><span class="muted">accepted 目标：${esc(g.accepted_goals.join("; ") || "无")}
      ${g.accepted_goal ? " · 锚点（只挑 accepted）：<b>" + esc(g.accepted_goal) + "</b> → " + g.accepted_rewards.map(x => x ? "✓" : "·").join("") : ""}</span></summary>
      <div class="body">加载中…</div></details>`).join("");
  document.querySelectorAll("details.group").forEach(d => d.addEventListener("toggle", () => { if (d.open) loadGroup(d); }, {once: true}));
}
function anchorBlock(name, a) {
  if (!a) return `<p>${name}：没有可选的锚点</p>`;
  if (!a.goal) return `<p>${name}：锚点 = 第 ${a.anchor} 局，LLM 结论 ${badge(a.status)} → 不改写</p>`;
  return `<p>${name}：锚点 = 第 ${a.anchor} 局，新目标 <b>${esc(a.instruction)}</b>（${esc(a.goal.join(" / "))}）<br>
    重新打分：${a.rewards.map(x => x ? '<span class="ok">✓</span>' : '<span class="no">✗</span>').join(" ")} · GRPO advantage：${a.advantages.join(", ")}</p>`;
}
function loadGroup(d) {
  fetch(`data/group_${d.dataset.group}.json`).then(r => r.json()).then(g => {
    let html = anchorBlock("LfH 锚点（失败局里随机挑）", g.uniform_anchor) + anchorBlock("只从 accepted 里挑的锚点", g.accepted_anchor);
    const s = INDEX.summary;
    html += `<table><tr><th>局</th><th>${esc(s.compare_version || "对比")}</th><th>LLM 结论（${esc(s.version)}）</th><th>LLM 给的目标 / 理由</th><th>状态检查器里的模板成果</th><th>半步成果</th><th>按该局目标重新打分</th><th>轨迹</th></tr>`;
    for (const e of g.episodes) {
      const llm = e.llm || {};
      const evidence = Array.isArray(llm.evidence_steps) ? llm.evidence_steps : [];
      html += `<tr><td>${e.index}</td><td>${e.compare_status ? badge(e.compare_status) + "<br><span class=muted>" + esc((e.compare_llm || {}).instruction || "") + "</span>" : "—"}</td><td>${badge(e.status)}</td><td><b>${esc(llm.instruction || "—")}</b><br><span class="muted">${esc(llm.reason || e.error || "")}</span>
        <br><span class="muted">证据步：${esc(evidence.join(", "))}</span></td>
        <td>${esc(e.state_goals.map(x => x.join(" / ")).join("; ") || "—")}</td><td>${esc(e.half.join("; ") || "—")}</td>
        <td>${e.rescored ? e.rescored.map(x => x ? '<span class="ok">✓</span>' : '<span class="no">✗</span>').join("") : "—"}</td>
        <td><details><summary>${e.steps} 步</summary><table class="traj">${e.trajectory.map((t, i) => {
          const ev = evidence.includes(i + 1) ? ' class="ev"' : "";
          return `<tr${ev}><td>${i + 1}</td><td>${esc(t.action)}${t.valid ? "" : ' <span class="muted">(格式无效)</span>'}</td><td>${esc(t.feedback)}</td><td><details><summary>模型原文</summary><pre>${esc(t.response)}</pre></details></td></tr>`;
        }).join("")}</table></details></td></tr>`;
    }
    d.querySelector(".body").innerHTML = html + "</table>";
  }).catch(() => {
    d.querySelector(".body").innerHTML = "加载失败，收起后再展开重试";
    d.addEventListener("toggle", () => { if (d.open) loadGroup(d); }, {once: true});
  });
}
</script></body></html>
"""

if __name__ == "__main__":
    main()
