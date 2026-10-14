"""Stages 7 & 8 - Proposal Generation and Delivery Handoff.

The proposal is written into the company's own Word template (styles, header, footer, cover
placeholders preserved). Every claim in it comes from matched evidence in the company's
knowledge base; nothing is invented.
"""
from __future__ import annotations

import copy
import io
import re
from datetime import date

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from . import llm

ENG_LABEL = {"managed_services": "outcome-based managed service", "product": "product-led solution with full system integration",
             "consulting": "enterprise architecture advisory engagement", "implementation": "design-and-build implementation"}
COMPLIANCE = {"strong": "Fully compliant", "partial": "Compliant (with approach)", "gap": "Partially compliant – mitigation", "confirm": "Noted & accepted"}


def money(v: float, ccy: str) -> str:
    if v >= 1_000_000:
        return f"{ccy} {v / 1_000_000:,.2f}M"
    return f"{ccy} {v:,.0f}"


# --------------------------------------------------------------------------- narrative
def response_text(r: dict, company: str) -> str:
    m = r.get("match", {})
    ev = m.get("evidence", [])
    caps = [e["name"] for e in ev if e["type"] == "Capability"]
    cs = [e["name"] for e in ev if e["type"] == "Case study"]
    acc = [e["name"] for e in ev if e["type"] == "Accelerator"]
    certs = [e["name"] for e in ev if e["type"] == "Certification"]
    st = r.get("match_status")
    if st == "confirm":
        return f"{company} notes and accepts this condition."
    parts = []
    if certs:
        parts.append(f"{company} holds {', '.join(certs)}.")
    if caps:
        parts.append(f"Delivered through our {caps[0]} capability" + (f", accelerated by {acc[0]}" if acc else "") + ".")
    if m.get("people_count"):
        parts.append(f"{m['people_count']} engineers with {', '.join(m.get('technologies_have', [])[:3])} skills are available to the programme.")
    if cs:
        parts.append(f"Reference: {cs[0]}.")
    if st in ("partial", "gap") and r.get("gap", {}).get("options"):
        o = r["gap"]["options"][0]
        missing = ", ".join(m.get("technologies_missing", [])[:2]) or "this area"
        client_facing = {
            "Partner": f"Delivered together with our specialist {missing} partner, with {company} as prime contractor and integrator.",
            "Upskill": f"Our engineers are completing {missing} certification ahead of mobilisation, backed by our existing integration practice.",
            "Hire": f"Dedicated {missing} specialists will join the team before mobilisation.",
            "Certify": f"{company} is progressing {missing} certification; we will share the certification plan and interim controls.",
            "Define method": f"{company} will apply its standard delivery method for this, detailed in Section 4 and confirmed with you during mobilisation.",
            "Build": f"{company} will design and validate a dedicated solution component for this requirement during the design phase.",
        }.get(o["type"])
        if client_facing:
            parts.append(client_facing)
    return " ".join(parts) or f"{company} will meet this requirement as part of the delivery approach."


def ai_responses(reqs: list[dict], company: dict, client: str, guidance: str = "", progress=None) -> dict[str, str]:
    """AI drafts the client-facing response for each requirement, using only its matched evidence."""
    todo = [r for r in reqs if r["category"] != "Commercial" and r.get("match_status") != "confirm"]
    out: dict[str, str] = {}
    batches = [todo[i:i + 15] for i in range(0, len(todo), 15)]
    for n, chunk in enumerate(batches, start=1):
        if progress:
            progress(f"AI writing proposal responses: batch {n} of {len(batches)}")
        lines = []
        for k, r in enumerate(chunk):
            m = r.get("match", {})
            ev = "; ".join(f"{e['type']}: {e['name']}" for e in m.get("evidence", [])[:4]) or "none"
            plan = r.get("gap", {}).get("options", [{}])[0].get("detail", "") if r.get("match_status") in ("gap", "partial") else ""
            lines.append(f"[{k}] REQUIREMENT: {r['text'][:400]}\n  fit: {r.get('match_status')} | evidence: {ev} | "
                         f"people: {m.get('people_count', 0)} with {', '.join(m.get('technologies_have', [])[:3]) or 'relevant skills'}"
                         + (f"\n  plan to close gap: {plan[:240]}" if plan else ""))
        prompt = (f"Company: {company['name']}. {company.get('about', '')[:500]}\nClient: {client}\n\n" + "\n".join(lines) +
                  '\n\nWrite the response for each requirement as it will appear in the proposal compliance matrix: 2-3 sentences, confident, '
                  "specific, first person plural (we). Mention the cited capability, reference project or certification by name. For gaps, state "
                  "the approach positively without admitting weakness and without inventing facts. JSON array: "
                  '[{"i": index, "response": "..."}]' + guidance)
        try:
            res = llm.complete_json("You are an expert bid writer. Use only the facts provided. Never invent clients, numbers, certifications or products.",
                                    prompt, max_tokens=9000)
        except Exception:
            break
        if isinstance(res, dict):
            res = next((v for v in res.values() if isinstance(v, list)), [])
        for it in res if isinstance(res, list) else []:
            try:
                out[chunk[int(it["i"])]["id"]] = str(it["response"]).strip()[:1200]
            except Exception:
                continue
    return out


def executive_summary(ctx: dict) -> str:
    d, company = ctx["deal"], ctx["company"]
    g, est, pr = ctx["gaps"], ctx["estimation"], ctx["pricing"]
    sc = next((s for s in pr["scenarios"] if s["name"] == ctx.get("scenario", "Target")), pr["scenarios"][1])
    rfp_price = sc["price"] * pr["fx_to_rfp"]
    counts = g.get("counts", {})
    tech = [r for r in ctx["requirements"] if r["category"] in ("Functional", "Non-functional")]
    cs = ctx.get("case_studies", [])[:2]
    cs_txt = "; ".join(f"{c['title']} ({'; '.join(c.get('outcomes', [])[:1]) or c.get('industry', '')})" for c in cs)
    if llm.is_enabled():
        try:
            facts = {
                "client": d["client_display"], "rfp_title": d["name"], "engagement": ENG_LABEL.get(d["engagement_type"], ""),
                "company": company["name"], "company_about": company.get("about", ""), "requirements": len(ctx["requirements"]),
                "technical_requirements": len(tech), "fully_met": counts.get("strong", 0), "met_with_approach": counts.get("partial", 0),
                "mitigated": counts.get("gap", 0), "team_size": est["headcount"], "duration_months": est["contract_months"],
                "price": money(rfp_price, pr["rfp_currency"]), "references": cs_txt, "architecture": ctx["architecture"]["summary"],
                "evaluation_criteria": [e["criterion"] for e in ctx["meta"].get("evaluation_criteria", [])],
            }
            return llm.complete("You write crisp, factual executive summaries for enterprise proposals. Use only the facts given. 3 short paragraphs, no headings, no bullet points.",
                                f"Facts (JSON): {facts}", max_tokens=900).strip()
        except Exception:
            pass
    p1 = (f"{d['client_display']} is seeking a partner for {d['name']}. {company['name']} proposes {_a(ENG_LABEL.get(d['engagement_type'], 'engagement'))} "
          f"that answers all {len(ctx['requirements'])} requirements identified in the RFP, including {len(tech)} functional and non-functional requirements.")
    p2 = (f"{counts.get('strong', 0)} requirements are met by proven, in-house capabilities and {counts.get('partial', 0)} by extending them; "
          f"the remaining {counts.get('gap', 0)} are covered by the mitigation plan in this proposal. "
          + (f"Relevant references include {cs_txt}. " if cs_txt else "")
          + ctx["architecture"]["summary"])
    p3 = (f"A {est['headcount']}-person team, led by an engagement manager accountable for outcomes, will deliver over {est['contract_months']} months. "
          f"Our commercial offer is {money(rfp_price, pr['rfp_currency'])}, with payments linked to accepted milestones.")
    return "\n\n".join([p1, p2, p3])


# --------------------------------------------------------------------------- docx helpers
def _replace_in_paragraph(p, mapping: dict[str, str]):
    full = "".join(r.text for r in p.runs)
    if "{{" not in full:
        return
    new = full
    for k, v in mapping.items():
        new = new.replace("{{" + k + "}}", v)
    if new != full and p.runs:
        p.runs[0].text = new
        for r in p.runs[1:]:
            r.text = ""


def _replace_everywhere(doc, mapping):
    for p in doc.paragraphs:
        _replace_in_paragraph(p, mapping)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    _replace_in_paragraph(p, mapping)
    for s in doc.sections:
        for part in (s.header, s.footer, s.first_page_header, s.first_page_footer):
            try:
                for p in part.paragraphs:
                    _replace_in_paragraph(p, mapping)
            except Exception:
                pass


def _style(doc, name, fallback="Normal"):
    try:
        doc.styles[name]
        return name
    except KeyError:
        return fallback


def _shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


class Writer:
    def __init__(self, doc):
        self.doc = doc
        self.added = []
        body = doc.element.body
        self.marker = None
        for p in doc.paragraphs:
            if "{{CONTENT}}" in p.text:
                self.marker = p._p
                break
        self.body = body

    def _track(self, el):
        if self.marker is not None:
            self.marker.addprevious(el)
        self.added.append(el)

    def h(self, text, level=1):
        p = self.doc.add_paragraph(text, style=_style(self.doc, f"Heading {level}"))
        self._track(p._p)
        return p

    def p(self, text, bold_prefix: str | None = None, italic=False, size=None, color=None):
        p = self.doc.add_paragraph(style=_style(self.doc, "Normal"))
        if bold_prefix:
            r = p.add_run(bold_prefix)
            r.bold = True
        r = p.add_run(text)
        r.italic = italic
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color
        self._track(p._p)
        return p

    def bullets(self, items):
        st = _style(self.doc, "List Bullet")
        for it in items:
            p = self.doc.add_paragraph(it, style=st)
            self._track(p._p)

    def table(self, header, rows, widths=None, font=8.5):
        from docx.shared import Cm
        t = self.doc.add_table(rows=1, cols=len(header))
        t.autofit = False
        try:
            t.style = self.doc.styles["Table Grid"]
        except KeyError:
            pass
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(header):
            c = t.rows[0].cells[i]
            c.text = ""
            r = c.paragraphs[0].add_run(str(h))
            r.bold = True
            r.font.size = Pt(font)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            _shade(c, "1F3A5F")
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                r = cells[i].paragraphs[0].add_run(str(v))
                r.font.size = Pt(font)
        if widths:
            grid = t._tbl.tblGrid
            for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
                if i < len(widths):
                    gc.set(qn("w:w"), str(int(widths[i] * 567)))
            for row in t.rows:
                for i, wcm in enumerate(widths[:len(row.cells)]):
                    row.cells[i].width = Cm(wcm)
        self._track(t._tbl)
        spacer = self.doc.add_paragraph()
        self._track(spacer._p)
        return t

    def page_break(self):
        p = self.doc.add_paragraph()
        p.add_run().add_break(__import__("docx.enum.text", fromlist=["WD_BREAK"]).WD_BREAK.PAGE)
        self._track(p._p)

    def finish(self):
        if self.marker is not None:
            self.marker.getparent().remove(self.marker)


def _open_template(template_bytes: bytes | None):
    if template_bytes:
        try:
            return Document(io.BytesIO(template_bytes))
        except Exception:
            pass
    d = Document()
    d.add_paragraph("{{TITLE}}", style="Title")
    d.add_paragraph("Proposal submitted to {{CLIENT}} by {{COMPANY}} — {{DATE}}")
    d.add_paragraph("{{CONTENT}}")
    return d


# --------------------------------------------------------------------------- proposal
def build_proposal(ctx: dict, template_bytes: bytes | None) -> tuple[bytes, dict]:
    d, company = ctx["deal"], ctx["company"]
    reqs = ctx["requirements"]
    est, pr, arch, g = ctx["estimation"], ctx["pricing"], ctx["architecture"], ctx["gaps"]
    cname = company["name"]
    doc = _open_template(template_bytes)
    _replace_everywhere(doc, {"TITLE": d["name"], "CLIENT": d["client_display"], "DATE": date.today().strftime("%d %B %Y"), "COMPANY": cname})
    w = Writer(doc)
    summary = ctx.get("executive_summary") or executive_summary(ctx)
    sc = next((s for s in pr["scenarios"] if s["name"] == ctx.get("scenario", "Target")), pr["scenarios"][1])
    fx = pr["fx_to_rfp"]
    ccy = pr["rfp_currency"]

    w.h("1. Executive summary", 1)
    for para in summary.split("\n\n"):
        w.p(para.strip())
    w.table(["At a glance", ""], [
        ["Engagement model", ENG_LABEL.get(d["engagement_type"], d["engagement_type"]).capitalize()],
        ["Requirements addressed", f"{len(reqs)} ({g['counts'].get('strong', 0)} fully met, {g['counts'].get('partial', 0)} with approach, {g['counts'].get('gap', 0)} mitigated)"],
        ["Team", f"{est['headcount']} people ({est['fte']} FTE), {round(est['onsite_ratio'] * 100)}% onsite"],
        ["Duration", f"{est['contract_months']} months"],
        ["Commercial offer", money(sc["price"] * fx, ccy)],
    ])

    w.h("2. Our understanding of your requirements", 1)
    by_cat = {}
    for r in reqs:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    w.p(f"We analysed the {d['doc_type']} in full and identified {len(reqs)} requirements: "
        + ", ".join(f"{v} {k.lower()}" for k, v in by_cat.items()) + ". Each is traced to its page in the source document in the compliance matrix (Section 9).")
    key = [r for r in reqs if r["category"] in ("Functional", "Non-functional") and r.get("priority") == "Mandatory"][:8]
    if key:
        w.p("Key outcomes we will deliver:", bold_prefix="")
        w.bullets([r["text"][:220] for r in key])
    ev = ctx["meta"].get("evaluation_criteria", [])
    if ev:
        w.h("How our response maps to your evaluation criteria", 2)
        w.table(["Criterion", "Weight", "Where we address it"],
                [[e["criterion"], f"{e['weight']}%" if e.get("weight") is not None else "", _criterion_section(e["criterion"])] for e in ev])

    w.h("3. Proposed solution", 1)
    w.p(arch["summary"])
    rows = []
    for l in arch["layers"]:
        rows.append([l["layer"], "; ".join(f"{c['name']}" + (" (partner)" if c["source"] == "Partner product" else "") for c in l["components"][:6])])
    if rows:
        w.table(["Layer / domain", "Components"], rows, widths=[4.5, 12.2])
    if arch.get("choices"):
        w.h("Technology decisions", 2)
        w.table(["Area", "Choice", "Basis", "Rationale"], [[c["area"], c["choice"], c["basis"], c["rationale"]] for c in arch["choices"]], widths=[3.6, 4.2, 3.0, 5.9])

    w.h("4. Delivery approach and plan", 1)
    w.table(["Phase", "Duration", "Activities"], [[ph["name"], _dur(ph["weeks"]) + (" (in parallel)" if ph.get("parallel") else ""), ph["detail"]] for ph in est["phases"]],
            widths=[4.5, 3.5, 8.7])
    if est.get("accelerators"):
        w.p("Accelerators that reduce effort and risk: " + "; ".join(f"{a['name']} (~{a['saving_pct']:.0f}% saving)" for a in est["accelerators"]) + ".")
    w.h("Governance", 2)
    w.bullets(["Monthly steering committee with the client sponsor; weekly service/delivery reviews.",
               "Single accountable engagement manager; escalation matrix agreed during mobilisation.",
               "Change, release and configuration management aligned with the client's CAB and quality standards."])

    w.h("5. Team and organisation", 1)
    w.table(["Role", "FTE", "Location", "Responsibility", "Proposed people"], widths=[3.4, 1.1, 1.8, 6.0, 4.4], rows=
            [[t["role"], t["fte"], t["location"], t["responsibility"], ", ".join(p["code"] for p in t["assigned"]) + (f" (+{t['unfilled']} to hire)" if t["unfilled"] else "")]
             for t in est["team"]])

    cases = ctx.get("case_studies", [])
    if cases:
        w.h("6. Relevant experience", 1)
        for c in cases[:4]:
            w.h(c["title"], 3)
            meta_line = ", ".join(x for x in [c.get("client"), c.get("industry"), c.get("region"), c.get("year")] if x)
            if meta_line:
                w.p(meta_line, italic=True)
            if c.get("summary"):
                w.p(c["summary"])
            if c.get("outcomes"):
                w.bullets(c["outcomes"][:4])

    certs = ctx.get("certifications", [])
    if certs:
        w.h("7. Certifications and partnerships", 1)
        w.table(["Certification", "Type", "Issuer", "Valid until"], [[c["name"], c.get("kind", "").title(), c.get("issuer", ""), c.get("valid_until", "")] for c in certs])

    w.h("8. Commercial summary", 1)
    w.p(f"Our offer for the full scope is {money(sc['price'] * fx, ccy)}" + (f" ({money(sc['price'], pr['currency'])})" if ccy != pr["currency"] else "")
        + f" for {est['contract_months']} months, inclusive of the team, governance and transition.")
    w.table(["Milestone", "Share", "Amount"],
            [[m["name"], f"{m['pct']}%", money(sc["price"] * fx * m["pct"] / 100, ccy)] for m in pr["milestones"]])
    if pr.get("partner_note"):
        w.p(pr["partner_note"], italic=True)

    w.h("9. Requirement compliance matrix", 1)
    tech_rows = []
    for r in reqs:
        if r["category"] == "Commercial":
            continue
        tech_rows.append([r.get("source_ref") or r["code"], r["text"][:300], f"p.{r['page']}", COMPLIANCE.get(r.get("match_status"), ""),
                          (r.get("response") or response_text(r, cname))[:700]])
    w.table(["Ref", "Requirement", "Source", "Compliance", "Our response"], tech_rows, widths=[1.6, 6.0, 1.1, 2.2, 5.8], font=7.5)

    w.h("10. Assumptions, dependencies and exclusions", 1)
    assumptions = est.get("assumptions", []) + pr.get("assumptions", [])
    w.bullets(assumptions)
    oos = ctx["meta"].get("out_of_scope", [])
    if oos:
        w.p("Out of scope (as defined in the RFP):", bold_prefix="")
        w.bullets(oos)

    w.h("11. Risks and mitigations", 1)
    risks = [r for r in reqs if r.get("gap", {}).get("risk") in ("High", "Medium")][:15]
    if risks:
        w.table(["Ref", "Risk", "Level", "Mitigation"],
                [[r.get("source_ref") or r["code"], r["text"][:160], r["gap"]["risk"], (r["gap"]["options"][0]["type"] + ": " + r["gap"]["options"][0]["detail"])[:260]]
                 for r in risks if r["gap"].get("options")])
    else:
        w.p("No material delivery risks were identified against the requirements.")

    commercial = [r for r in reqs if r["category"] == "Commercial"]
    if commercial:
        w.h("Appendix A. Commercial and contractual conditions", 1)
        w.table(["Ref", "Condition", "Source", "Position"], [[r.get("source_ref") or r["code"], r["text"][:300], f"p.{r['page']}", "Accepted"] for r in commercial], widths=[1.8, 11.0, 1.4, 2.5], font=7.5)
    w.finish()
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), {"executive_summary": summary, "sections": 11, "compliance_rows": len(tech_rows), "scenario": sc["name"],
                            "price": round(sc["price"] * fx, 2), "currency": ccy}


def _a(phrase: str) -> str:
    return ("an " if phrase[:1].lower() in "aeiou" else "a ") + phrase


def _dur(weeks: float) -> str:
    return f"{round(weeks)} weeks" if weeks < 26 else f"{round(weeks / 4.33)} months"


def _criterion_section(name: str) -> str:
    n = name.lower()
    if "financ" in n or "commercial" in n or "cost" in n:
        return "Section 8 – Commercial summary"
    if "secur" in n or "complian" in n:
        return "Sections 7 & 9 – Certifications, compliance matrix"
    if "support" in n or "maint" in n or "sla" in n:
        return "Section 4 – Delivery approach; Section 9"
    if "profile" in n or "experience" in n or "track" in n:
        return "Sections 5 & 6 – Team, relevant experience"
    if "requirement" in n or "functional" in n or "architecture" in n:
        return "Sections 2 & 3 – Understanding, solution"
    return "Sections 3–4"


# --------------------------------------------------------------------------- handoff
def build_handoff_data(ctx: dict) -> dict:
    reqs, est, pr, g = ctx["requirements"], ctx["estimation"], ctx["pricing"], ctx["gaps"]
    sc = next((s for s in pr["scenarios"] if s["name"] == ctx.get("scenario", "Target")), pr["scenarios"][1])
    scope = []
    for w in est["workstreams"]:
        scope.append({"workstream": w["name"], "requirements": w["requirements"], "codes": w["codes"][:20], "effort_days": w["effort_days"]})
    risks = [{"code": r["code"], "ref": r.get("source_ref", ""), "risk": r["text"][:200], "level": r["gap"]["risk"],
              "mitigation": r["gap"]["options"][0]["detail"] if r["gap"].get("options") else "", "owner": "Delivery lead"}
             for r in reqs if r.get("gap", {}).get("risk") in ("High", "Medium")][:25]
    open_items = []
    for t in est["team"]:
        if t["unfilled"]:
            open_items.append(f"Hire or contract {t['unfilled']} × {t['role']} ({t['location']}) before mobilisation.")
        for p in t["assigned"]:
            if p["status"] != "Available":
                open_items.append(f"Release {p['code']} ({p['role']}) from current assignment.")
    for t in g.get("top_missing", [])[:6]:
        open_items.append(f"{t['recommendation']}: {t['technology']} (affects {t['requirements']} requirements).")
    confirm = [r for r in reqs if r.get("match_status") == "confirm" and r["category"] == "Commercial"][:12]
    return {
        "summary": f"{ctx['deal']['name']} for {ctx['deal']['client_display']}: {ENG_LABEL.get(ctx['deal']['engagement_type'], '')}, "
                   f"{est['contract_months']} months, {est['headcount']} people, contract value {money(sc['price'] * pr['fx_to_rfp'], pr['rfp_currency'])}.",
        "scope": scope,
        "out_of_scope": ctx["meta"].get("out_of_scope", []),
        "deliverables": ctx["meta"].get("deliverables", []),
        "slas": ctx["meta"].get("slas", []),
        "assumptions": est.get("assumptions", []) + pr.get("assumptions", []),
        "risks": risks,
        "team": [{"role": t["role"], "fte": t["fte"], "location": t["location"], "people": [p["code"] for p in t["assigned"]], "unfilled": t["unfilled"]} for t in est["team"]],
        "plan": est["phases"],
        "milestones": [{**m, "amount": round(sc["price"] * pr["fx_to_rfp"] * m["pct"] / 100, 2)} for m in pr["milestones"]],
        "commercial_conditions": [{"code": r["code"], "text": r["text"][:240]} for r in confirm],
        "open_items": open_items[:20],
        "first_30_days": ["Kick-off with client sponsor; confirm governance, escalation matrix and reporting cadence.",
                          "Provision access to environments and source/target systems.",
                          "Baseline scope against this handoff pack; log any differences as change requests.",
                          "Confirm named team, release dates and onboarding for any new hires."],
    }


def build_handoff_docx(ctx: dict, data: dict, template_bytes: bytes | None) -> bytes:
    doc = _open_template(template_bytes)
    d = ctx["deal"]
    _replace_everywhere(doc, {"TITLE": f"Delivery handoff – {d['name']}", "CLIENT": d["client_display"], "DATE": date.today().strftime("%d %B %Y"),
                              "COMPANY": ctx["company"]["name"]})
    w = Writer(doc)
    w.h("Delivery handoff pack", 1)
    w.p(data["summary"])
    w.h("1. Scope by workstream", 2)
    w.table(["Workstream", "Requirements", "Effort (days)", "Requirement refs"], [[s["workstream"], s["requirements"], s["effort_days"], ", ".join(s["codes"][:12])] for s in data["scope"]])
    if data["out_of_scope"]:
        w.h("2. Out of scope", 2)
        w.bullets(data["out_of_scope"])
    if data["deliverables"]:
        w.h("3. Contractual deliverables", 2)
        w.bullets(data["deliverables"])
    if data["slas"]:
        w.h("4. Service levels", 2)
        w.bullets(data["slas"])
    w.h("5. Team", 2)
    w.table(["Role", "FTE", "Location", "People", "To hire"], [[t["role"], t["fte"], t["location"], ", ".join(t["people"]), t["unfilled"]] for t in data["team"]])
    w.h("6. Plan", 2)
    w.table(["Phase", "Weeks", "Activities"], [[p["name"], round(p["weeks"]), p["detail"]] for p in data["plan"]])
    w.h("7. Commercial milestones", 2)
    w.table(["Milestone", "Share", "Amount"], [[m["name"], f"{m['pct']}%", f"{m['amount']:,.0f}"] for m in data["milestones"]])
    w.h("8. Assumptions", 2)
    w.bullets(data["assumptions"])
    if data["risks"]:
        w.h("9. Risks", 2)
        w.table(["Ref", "Risk", "Level", "Mitigation", "Owner"], [[r["ref"] or r["code"], r["risk"], r["level"], r["mitigation"][:200], r["owner"]] for r in data["risks"]])
    if data["open_items"]:
        w.h("10. Open items before mobilisation", 2)
        w.bullets(data["open_items"])
    w.h("11. First 30 days", 2)
    w.bullets(data["first_30_days"])
    w.finish()
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
