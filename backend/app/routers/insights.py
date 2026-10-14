"""Management dashboard and the knowledge-graph API."""
from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..models import Capability, CaseStudy, Deal, DealStage, Employee, GraphEdge, GraphNode, Requirement
from ..security import Ctx, current_ctx
from ..services.solution import FX_PER_USD
from ..services import graph, llm
from ..services.masking import deal_masker

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/dashboard")
def dashboard(ctx: Ctx = Depends(current_ctx)):
    tid = ctx.tenant_id
    deals = ctx.db.scalars(select(Deal).where(Deal.tenant_id == tid).order_by(Deal.created_at.desc())).all()
    stages = defaultdict(dict)
    for s in ctx.db.scalars(select(DealStage).where(DealStage.tenant_id == tid)):
        stages[s.deal_id][s.stage] = s
    pipeline_value = 0.0
    weighted = 0.0
    rows = []
    status_counts = Counter(d.status for d in deals)
    readiness = []
    first_draft = []
    for d in deals:
        st = stages.get(d.id, {})
        pr = st.get("pricing").data if "pricing" in st else {}
        g = st.get("gaps").data if "gaps" in st else {}
        sel = next((s for s in pr.get("scenarios", []) if s["name"] == pr.get("selected", "Target")), None) if pr else None
        base = pr.get("currency") or ctx.tenant.currency or "USD"
        price = sel["price"] if sel else 0
        # pipeline totals in the company's currency; each deal shown in its RFP's currency
        val_usd = price / FX_PER_USD.get(base, 1) * FX_PER_USD.get(ctx.tenant.currency or "USD", 1)
        deal_val, deal_ccy = price * pr.get("fx_to_rfp", 1), pr.get("rfp_currency") or base
        if d.status not in ("lost", "no_bid"):
            pipeline_value += val_usd
            weighted += val_usd * (g.get("mitigated_readiness", 50) / 100)
        if g.get("readiness") is not None:
            readiness.append(g["mitigated_readiness"])
        if (d.meta or {}).get("first_draft_seconds"):
            first_draft.append(d.meta["first_draft_seconds"])
        approved = sum(1 for s in st.values() if s.status == "approved")
        mask = deal_masker(d)
        rows.append({"id": d.id, "name": mask(d.name), "client": d.client_alias if d.confidential else d.client_name, "status": d.status,
                     "industry": d.industry, "engagement_type": d.engagement_type, "value": deal_val if sel else 0, "value_currency": deal_ccy if sel else None, "margin_pct": sel["margin_pct"] if sel else None,
                     "coverage_pct": g.get("coverage_pct"), "readiness": g.get("mitigated_readiness"), "verdict": g.get("verdict"),
                     "approved_stages": approved, "created_at": d.created_at, "due_date": d.due_date})
    reqs = ctx.db.scalars(select(Requirement).where(Requirement.tenant_id == tid)).all()
    per_deal = defaultdict(Counter)
    for r in reqs:
        if r.match_status:
            per_deal[r.deal_id][r.match_status] += 1
    for row in rows:
        row["match_mix"] = dict(per_deal.get(row["id"], {}))
    cat = Counter(r.category for r in reqs)
    match = Counter(r.match_status for r in reqs if r.match_status)
    reviewed = [r for r in reqs if r.verified]
    acc = round(sum(1 for r in reviewed if r.category == r.original_category) / len(reviewed) * 100, 1) if reviewed else None
    missing = Counter()
    for r in reqs:
        for t in (r.match or {}).get("technologies_missing", []):
            missing[t] += 1
    demand = Counter()
    for r in reqs:
        for e in (r.match or {}).get("evidence", [])[:1]:
            if e["type"] == "Capability":
                demand[e["name"]] += 1
    won = status_counts.get("won", 0)
    lost = status_counts.get("lost", 0)
    team = ctx.db.scalar(select(func.count()).select_from(Employee).where(Employee.tenant_id == tid))
    bench = ctx.db.scalar(select(func.count()).select_from(Employee).where(Employee.tenant_id == tid, Employee.availability >= 50))
    return {
        "kpis": {"deals": len(deals), "active": sum(1 for d in deals if d.status in ("processing", "in_review", "submitted")),
                 "pipeline_value": round(pipeline_value, 2), "weighted_pipeline": round(weighted, 2), "currency": ctx.tenant.currency,
                 "requirements": len(reqs), "avg_readiness": round(sum(readiness) / len(readiness)) if readiness else None,
                 "avg_first_draft_seconds": round(sum(first_draft) / len(first_draft), 1) if first_draft else None,
                 "win_rate": round(won / (won + lost) * 100) if (won + lost) else None, "won": won, "lost": lost,
                 "classification_accuracy": acc, "reviewed": len(reviewed), "people": team, "available_people": bench},
        "deals": rows[:50],
        "status_counts": dict(status_counts),
        "requirement_categories": dict(cat),
        "match_mix": dict(match),
        "skill_gaps": [{"technology": t, "requirements": n} for t, n in missing.most_common(10)],
        "capability_demand": [{"capability": c, "requirements": n} for c, n in demand.most_common(8)],
        "llm": llm.status(),
    }


@router.get("/graph")
def get_graph(deal_id: str | None = None, types: str = "", ctx: Ctx = Depends(current_ctx)):
    tl = [t for t in types.split(",") if t] or None
    data = graph.subgraph(ctx.db, ctx.tenant_id, deal_id, tl)
    counts = Counter(n["type"] for n in data["nodes"])
    total_nodes = ctx.db.scalar(select(func.count()).select_from(GraphNode).where(GraphNode.tenant_id == ctx.tenant_id))
    total_edges = ctx.db.scalar(select(func.count()).select_from(GraphEdge).where(GraphEdge.tenant_id == ctx.tenant_id))
    return {**data, "counts": dict(counts), "totals": {"nodes": total_nodes, "edges": total_edges}}


@router.get("/graph/node")
def node_detail(key: str, ctx: Ctx = Depends(current_ctx)):
    n = ctx.db.scalar(select(GraphNode).where(GraphNode.tenant_id == ctx.tenant_id, GraphNode.key == key))
    if not n:
        return None
    edges = ctx.db.scalars(select(GraphEdge).where(GraphEdge.tenant_id == ctx.tenant_id, (GraphEdge.src == key) | (GraphEdge.dst == key))).all()
    other = {e.dst if e.src == key else e.src for e in edges}
    labels = {x.key: (x.type, x.label) for x in ctx.db.scalars(select(GraphNode).where(GraphNode.tenant_id == ctx.tenant_id, GraphNode.key.in_(other)))}
    return {"id": n.key, "type": n.type, "label": n.label, "props": n.props,
            "links": [{"rel": e.rel, "direction": "out" if e.src == key else "in", "id": e.dst if e.src == key else e.src,
                       "type": labels.get(e.dst if e.src == key else e.src, ("", ""))[0],
                       "label": labels.get(e.dst if e.src == key else e.src, ("", ""))[1]} for e in edges][:80]}
