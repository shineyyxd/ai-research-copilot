# -*- coding: utf-8 -*-
"""
harness.py — 零依赖 Agent Harness（LangGraph 风格的节点图运行时）

把 v1 的"单脚本 for 循环"升级为节点式执行图，提供四件 v1 没有的东西：
  1. 节点编排：supervisor → planner → [interrupt 人工审批] → researcher → critic → reporter
  2. SQLite Checkpointer：每个节点完成后落盘，崩溃/中断后可从断点恢复
  3. 审计日志：每次检索工具调用的入参/出参/耗时写 JSONL，全程可查
  4. 人工审批点（interrupt）：计划生成后暂停，人编辑计划文件后放行（可选）

设计取舍：延续项目"纯标准库"签名，不引入 langgraph 包；
节点语义与 LangGraph 对齐（StateGraph + nodes + checkpointer），
后续迁移到官方 LangGraph 只需替换本文件的执行器，节点函数原样保留。
"""
import json, os, sqlite3, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("OUT_DIR", ROOT.parent / "output"))
OUT.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("CHECKPOINT_DB", OUT / "checkpoints.db"))
AUDIT_PATH = Path(os.environ.get("AUDIT_LOG", OUT / "audit_log.jsonl"))


class Checkpointer:
    """SQLite 断点存储：thread_id → (node, state_json)。"""

    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS checkpoints "
            "(thread_id TEXT, node TEXT, state TEXT, updated_at REAL, "
            "PRIMARY KEY (thread_id, node))")
        self.conn.commit()

    def save(self, thread_id, node, state):
        self.conn.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?)",
            (thread_id, node, json.dumps(state, ensure_ascii=False), time.time()))
        self.conn.commit()

    def load(self, thread_id):
        """返回 (最后完成的 node, state)；无记录返回 (None, None)。"""
        row = self.conn.execute(
            "SELECT node, state FROM checkpoints WHERE thread_id=? "
            "ORDER BY updated_at DESC LIMIT 1", (thread_id,)).fetchone()
        return (row[0], json.loads(row[1])) if row else (None, None)


def audit(tool, params, result_meta):
    """每次工具调用写一行审计日志（入参 + 结果元信息 + 时间戳）。"""
    rec = {"ts": round(time.time(), 3), "tool": tool,
           "params": params, "result": result_meta}
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


class Graph:
    """极简节点图执行器：按 nodes 顺序执行，node 间以 state 传递；
    每个节点完成后写 checkpoint；interrupt_before 节点前暂停等待审批。"""

    def __init__(self, nodes, order, interrupt_before=None, checkpointer=None):
        self.nodes = nodes            # {name: fn(state) -> state}
        self.order = order            # [name, ...] 执行顺序
        self.interrupt_before = interrupt_before or set()
        self.cp = checkpointer or Checkpointer()

    def run(self, thread_id, state):
        last_node, saved = self.cp.load(thread_id)
        if saved is not None:
            state = saved
            start = self.order.index(last_node) + 1
            print(f"[harness] 从断点恢复：已完成到 {last_node}，续跑 {self.order[start:]}")
        else:
            start = 0
        for name in self.order[start:]:
            if name in self.interrupt_before and not state.get("_approved"):
                self.cp.save(thread_id, f"_wait_{name}", state)
                plan_file = OUT / f"plan_{thread_id}.json"
                plan_file.write_text(json.dumps(state.get("subs", state), ensure_ascii=False, indent=2),
                                     encoding="utf-8")
                print(f"[harness] interrupt：等待人工审批。编辑 {plan_file} 后，"
                      f"置 APPROVED=1 重跑即放行。")
                if os.environ.get("APPROVED") != "1":
                    return state, False   # 未批准，暂停（state 已落盘）
                state["_approved"] = True
            t0 = time.time()
            state = self.nodes[name](state)
            audit(f"node:{name}", {"thread": thread_id},
                  {"elapsed_s": round(time.time() - t0, 3),
                   "keys": sorted(state.keys())[:12]})
            self.cp.save(thread_id, name, state)
        return state, True
