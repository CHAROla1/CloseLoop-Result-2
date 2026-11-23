#!/usr/bin/env python3
"""提取闭环评测批次的每帧中间结果与场景 GT 自车轨迹到 CloseLoop-Result/perframe/。

用法：修改下方 SRC / REG_V5 / REG_V6 / DST 四个常量后 `python3 extract_perframe.py`。

- 遍历主批次 registry 的全部 task；
- 主批次中提前终止（缺 vlm_reasoning.jsonl）的任务，若同场景在重跑批次 registry
  （REG_V6）有成功运行，则整体改用重跑批次的 run 数据（csv/steps/vlm/metrics 同源，
  保证单任务数据自洽）；无重跑批次可置 REG_V6 = None；
- GT 自车轨迹始终取 data/scenes/<sample>/trajectories/ego.json（与 run 无关）。

首次使用：2026-11-13-v5（64 task，其中 8 个取自 2026-11-13-v6 重跑），
产出结构见 perframe/2026-11-13-v5/README.md。
"""
import csv
import glob
import json
import os
import shutil

SRC = "/mnt/workspace/WM_Group/tang-workspace/alpasim_render_bk/Alpasim_WorldModel_ClosedLoop"
REG_V5 = f"{SRC}/cluster_config/cluster_registry/2026-11-13-v5"
REG_V6 = f"{SRC}/cluster_config/cluster_registry/2026-11-13-v6"
DST = "/mnt/workspace/WM_Group/tang-workspace/CloseLoop-Result/perframe/2026-11-13-v5"

STEPS_FIELDS = [
    "step", "time_now_us", "time_query_us", "t0_us", "scene_id",
    "anchor_pose", "trajectory_rig_xyz", "trajectory_rig_heading",
    "trajectory_local", "selected_candidate",
]


def task_map(reg):
    """registry tasks/*.json -> {task_id: (sample, state)}"""
    out = {}
    for tf in sorted(glob.glob(f"{reg}/tasks/task-*.json")):
        with open(tf) as f:
            t = json.load(f)
        out[os.path.basename(tf)[:-5]] = (t["task"]["sample"], t.get("state"))
    return out


def one(pattern):
    hits = glob.glob(pattern)
    return hits[0] if len(hits) == 1 else None


def main():
    v5 = task_map(REG_V5)
    v6 = task_map(REG_V6)
    v6_by_sample = {s: tid for tid, (s, st) in v6.items() if st == "succeeded"}

    with open(f"{SRC}/data/samples.json") as f:
        samples = json.load(f)

    os.makedirs(f"{DST}/tasks", exist_ok=True)
    rows, rerun, incomplete = [], [], []

    for tid, (sample, state) in v5.items():
        run = f"{REG_V5}/runs/{tid}"
        src_reg, src_tid = "2026-11-13-v5", tid
        # v5 run 数据不完整时改用 v6 重跑
        if one(f"{run}/rollout/rollouts/*/*/vlm_reasoning.jsonl") is None:
            alt = v6_by_sample.get(sample)
            if alt and one(f"{REG_V6}/runs/{alt}/rollout/rollouts/*/*/vlm_reasoning.jsonl"):
                src_reg, src_tid, run = "2026-11-13-v6", alt, f"{REG_V6}/runs/{alt}"
                rerun.append((tid, sample, alt))

        out = f"{DST}/tasks/{tid}"
        os.makedirs(out, exist_ok=True)
        got = []

        f_csv = one(f"{run}/rollout/alpasim_controller_*.csv")
        if f_csv:
            shutil.copy2(f_csv, f"{out}/ego_trajectory.csv")
            got.append("ego")

        f_steps = one(f"{run}/driver/out/*/steps.jsonl")
        if f_steps:
            with open(f_steps) as fi, open(f"{out}/planned_trajectories.jsonl", "w") as fo:
                for line in fi:
                    s = json.loads(line)
                    fo.write(json.dumps({k: s.get(k) for k in STEPS_FIELDS},
                                        ensure_ascii=False, separators=(",", ":")) + "\n")
            got.append("plan")

        f_vlm = one(f"{run}/rollout/rollouts/*/*/vlm_reasoning.jsonl")
        if f_vlm:
            shutil.copy2(f_vlm, f"{out}/vlm_reasoning.jsonl")
            got.append("vlm")

        f_metr = one(f"{run}/rollout/rollouts/*/*/metrics.parquet")
        if f_metr:
            shutil.copy2(f_metr, f"{out}/metrics.parquet")
            got.append("metrics")

        gt = f"{SRC}/data/scenes/{sample}/trajectories/ego.json"
        if os.path.exists(gt):
            shutil.copy2(gt, f"{out}/gt_ego_trajectory.json")
            got.append("gt")
        else:
            incomplete.append((tid, sample, "gt missing"))

        if len(got) < 5:
            incomplete.append((tid, sample, f"only {got}"))

        meta = samples.get(sample, {})
        rows.append({
            "task_id": tid, "sample": sample,
            "source_name": meta.get("source_name", ""),
            "scene_id": meta.get("scene_id", ""),
            "source_registry": src_reg, "source_task": src_tid,
        })

    with open(f"{DST}/mapping.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"tasks: {len(rows)}, rerun-from-v6: {len(rerun)}")
    for tid, sample, alt in rerun:
        print(f"  v5 {tid} ({sample}) <- v6 {alt}")
    print(f"incomplete: {incomplete if incomplete else 'none'}")


if __name__ == "__main__":
    main()
