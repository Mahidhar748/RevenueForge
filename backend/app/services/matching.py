"""Stages 2 & 3 - Capability Matching and Gap Analysis.

Each requirement is scored against the company's own knowledge: capabilities, case studies,
accelerators, certifications and the skills of its people. Every match carries the evidence it
was based on, so proposals can cite real assets rather than invent them.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import knowledge as K
from . import llm


@dataclass
class CompanyKB:
    name: str
    capabilities: list[dict] = field(default_factory=list)
    case_studies: list[dict] = field(default_factory=list)
    accelerators: list[dict] = field(default_factory=list)
    certifications: list[dict] = field(default_factory=list)
    employees: list[dict] = field(default_factory=list)
    rates: list[dict] = field(default_factory=list)
    won_capabilities: dict[str, int] = field(default_factory=dict)  # capability id -> wins (learning loop)

    def tech_inventory(self) -> dict[str, dict]:
        """tech -> {people, avg_level, capabilities, case_studies}"""
        inv: dict[str, dict] = defaultdict(lambda: {"people": 0, "levels": [], "capabilities": [], "case_studies": [], "available": 0})
        for e in self.employees:
            for s in e.get("skills", []):
                t = K.canonical_tech(s["name"])
                if s.get("level", 0) >= 2:
                    inv[t]["people"] += 1
                    inv[t]["levels"].append(s.get("level", 3))
                    if e.get("availability", 100) >= 50:
                        inv[t]["available"] += 1
        for c in self.capabilities:
            for t in c.get("technologies", []):
                inv[K.canonical_tech(t)]["capabilities"].append(c["name"])
        for cs in self.case_studies:
            for t in cs.get("technologies", []):
                inv[K.canonical_tech(t)]["case_studies"].append(cs["title"])
        out = {}
        for t, v in inv.items():
            out[t] = {"people": v["people"], "available": v["available"],
                      "avg_level": round(sum(v["levels"]) / len(v["levels"]), 1) if v["levels"] else 0,
                      "capabilities": sorted(set(v["capabilities"])), "case_studies": sorted(set(v["case_studies"]))}
        return out


def _cap_text(c):
    return f"{c['name']} {c.get('service_line', '')} {c.get('description', '')} {' '.join(c.get('technologies', []))} {' '.join(c.get('industries', []))}"


def _cs_text(c):
    return f"{c['title']} {c.get('summary', '')} {' '.join(c.get('technologies', []))} {' '.join(c.get('outcomes', []))} {c.get('industry', '')}"


def _acc_text(a):
    return f"{a['name']} {a.get('description', '')} {' '.join(a.get('technologies', []))}"


# Requirement-type context added to the query so short operational requirements find the right capability.
SUBCAT_CONTEXT = {
    "Service Levels": "sla service levels managed services incident support operations 24x7 response resolution",
    "Monitoring & Operations": "monitoring operations managed services alerts queues health checks support platform",
    "Maintainability & Quality": "devops release management version control change management documentation runbooks",
    "Availability & Continuity": "disaster recovery business continuity high availability failover backup resilience",
    "Performance & Scalability": "performance tuning capacity planning scalability platform engineering",
    "Transition & Knowledge Transfer": "transition knowledge transfer onboarding incumbent baselining runbooks governance",
    "Project Management": "delivery governance project management agile sprint reporting service review",
    "Testing & QA": "testing validation quality assurance test evidence go-live",
    "Support & Incident Management": "incident problem management rca support managed services troubleshooting",
    "Security": "security encryption access control audit logging iam",
    "Integration & APIs": "integration interfaces apis middleware messaging",
    "Architecture & Advisory": "architecture assessment roadmap advisory target state",
    "Data & Analytics": "data analytics reporting dashboards",
    "Fraud & Risk Analytics": "fraud risk analytics detection scoring",
    "Application Development": "application development engineering build configure",
}
PROCESS_RE = re.compile(r"\b(tender(er)?s?|bidders?|proposers?|proposals?|offer|rfp|rfi|documents?|notification|addend|clarification|address|"
                        r"visit|examine|alteration|value-added|complimentary|methods? statement|aggregates)\b", re.I)

ISO_RE = re.compile(r"iso\s*/?\s*(?:iec\s*)?(\d{4,5})", re.I)
CONFIRM_SUBS = {"Pricing & Payment", "Bonds & Guarantees", "Insurance & Liability", "Contract Terms", "Evaluation & Award", "Submission"}


def match_requirements(reqs: list[dict], kb: CompanyKB, engagement_type: str = "", industry: str = "", similarity=None,
                       guidance: str = "", progress=None) -> list[dict]:
    """Adds match_status, match_score and match evidence to each requirement dict (in place) and returns them.

    similarity: optional callable(queries, docs) -> (matrix, method) supplying semantic (embedding) similarity.
    """
    inv = kb.tech_inventory()
    company_techs = {t for t, v in inv.items() if v["people"] or v["capabilities"]}
    caps, css, accs = kb.capabilities, kb.case_studies, kb.accelerators
    docs = [K.expand(_cap_text(c)) for c in caps] + [K.expand(_cs_text(c)) for c in css] + [K.expand(_acc_text(a)) for a in accs]
    qtexts = [K.expand(f"{r['text']} {r.get('section', '')} {' '.join(r.get('technologies', []))} {SUBCAT_CONTEXT.get(r.get('subcategory', ''), '')}") for r in reqs]
    if not docs:
        docs = ["empty"]
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1)
    vec.fit(docs + qtexts)
    D = vec.transform(docs)
    Q = vec.transform(qtexts)
    sims = cosine_similarity(Q, D) if len(reqs) else []
    method = "tfidf"
    if similarity is not None and len(reqs) and docs != ["empty"]:
        raw_docs = [_cap_text(c) for c in caps] + [_cs_text(c) for c in css] + [_acc_text(a) for a in accs]
        raw_q = [f"{r['text']} ({r.get('section', '')})" for r in reqs]
        emb, method = similarity(raw_q, raw_docs)
        if method == "embeddings":
            # Map embedding cosine onto the same 0..~0.35 scale the scorer expects, and keep the better of the two signals.
            sims = [[max(t, max(0.0, (e - 0.55)) * 1.1) for t, e in zip(trow, erow)] for trow, erow in zip(sims, emb)]
    nc, ncs = len(caps), len(css)
    company_iso = {m.group(1) for c in kb.certifications for m in [ISO_RE.search(c["name"])] if m}

    for i, r in enumerate(reqs):
        row = sims[i] if len(reqs) else []
        cap_scores = sorted(((row[j], j) for j in range(nc)), reverse=True)[:3]
        cs_scores = sorted(((row[nc + j], j) for j in range(ncs)), reverse=True)[:2]
        acc_scores = sorted(((row[nc + ncs + j], j) for j in range(len(accs))), reverse=True)[:1]

        def norm(s, scale=0.32):
            return max(0.0, min(1.0, s / scale))

        best_cap = cap_scores[0] if cap_scores else (0, None)
        cap_s = norm(best_cap[0])
        if best_cap[1] is not None and caps[best_cap[1]].get("id") in kb.won_capabilities:
            cap_s = min(1.0, cap_s + 0.05)  # learning loop: capabilities that helped win before get a small boost
        cs_s = norm(cs_scores[0][0], 0.28) if cs_scores else 0
        req_techs = [t for t in r.get("technologies", []) if t not in K.COMMODITY_TECH]
        have = [t for t in req_techs if t in company_techs]
        missing = [t for t in req_techs if t not in company_techs]
        tech_cov = (len(have) / len(req_techs)) if req_techs else None
        people = sorted({e["code"] for e in kb.employees for s in e.get("skills", []) if s["name"] in have and s.get("level", 0) >= 3})

        industry_bonus = 0.04 if industry and any(industry.lower() in " ".join(c.get("industries", [])).lower() for c in caps) else 0
        if tech_cov is None:
            score = 0.72 * cap_s + 0.28 * cs_s + industry_bonus
        else:
            score = 0.45 * cap_s + 0.15 * cs_s + 0.40 * tech_cov
        score = round(min(0.99, score + (0.05 if people else 0)), 2)

        evidence = []
        for s, j in cap_scores:
            if s > 0.06:
                evidence.append({"type": "Capability", "id": caps[j].get("id", ""), "name": caps[j]["name"], "score": round(norm(s), 2)})
        for s, j in cs_scores:
            if s > 0.06:
                evidence.append({"type": "Case study", "id": css[j].get("id", ""), "name": css[j]["title"], "score": round(norm(s, 0.28), 2)})
        for s, j in acc_scores:
            if s > 0.08:
                evidence.append({"type": "Accelerator", "id": accs[j].get("id", ""), "name": accs[j]["name"], "score": round(norm(s), 2),
                                 "saving": accs[j].get("effort_saving_pct", 0)})

        status = "strong" if score >= 0.62 else "partial" if score >= 0.35 else "gap"
        if missing and status == "strong":
            status = "partial"
        rationale = []

        sub = r.get("subcategory", "")
        # Certification / standards requirements are checked against the certificate register.
        isos = set(ISO_RE.findall(r["text"]))
        if isos:
            held = sorted(isos & company_iso)
            lacking = sorted(isos - company_iso)
            certs = [c["name"] for c in kb.certifications if (m := ISO_RE.search(c["name"])) and m.group(1) in held]
            evidence = [{"type": "Certification", "name": c, "score": 1.0} for c in certs] + evidence[:1]
            if lacking:
                status, score = ("partial", 0.5) if held else ("gap", 0.15)
                missing = missing + [f"ISO {x}" for x in lacking]
                rationale.append(f"Holds {', '.join('ISO ' + h for h in held) or 'none'} of the requested standards; missing {', '.join('ISO ' + x for x in lacking)}.")
            else:
                status, score = "strong", 0.95
                rationale.append(f"Certified: {', '.join(certs)}.")
        elif sub in CONFIRM_SUBS or (r.get("category") == "Commercial"):
            status = "confirm"
            rationale.append("Commercial or submission condition: confirm acceptance with finance/legal; no capability gap.")
            if sub == "Evaluation & Award":
                rationale[-1] = "Evaluation criterion: shape win themes and evidence around it."
        elif r.get("category") == "Compliance" and sub in ("Regulatory", "Data Protection & Privacy", "Information Security Policy",
                                                          "Accessibility & Sustainability"):
            if status == "gap":
                status = "confirm"
                rationale.append("Policy or regulatory obligation: confirm compliance position with legal/security.")
        if r.get("category") == "Functional" and sub == "Team & Experience":
            same_ind = [c for c in css if industry and industry.lower() in (c.get("industry", "") + " " + c.get("summary", "")).lower()]
            evidence = [{"type": "Case study", "id": c.get("id", ""), "name": c["title"], "score": 0.9} for c in (same_ind or css)[:3]] + \
                       [e for e in evidence if e["type"] != "Case study"]
            status, score = ("strong", 0.85) if len(same_ind) >= 2 else ("partial", 0.55) if css else ("gap", 0.1)
            rationale.append(f"{len(same_ind)} reference projects in {industry or 'this industry'} and {len(kb.employees)} people in the skills register.")
        elif status == "gap" and not req_techs and not isos and PROCESS_RE.search(r["text"]) and r.get("category") != "Non-functional":
            status = "confirm"
            rationale.append("Response or tender-process obligation: answer in the proposal; no capability needed.")

        if status in ("strong", "partial") and not rationale:
            top = evidence[0]["name"] if evidence else "related capabilities"
            bits = [f"Best match: {top}"]
            if people:
                bits.append(f"{len(people)} people with {', '.join(have[:3])} skills")
            if missing:
                bits.append(f"not covered: {', '.join(missing)}")
            rationale.append("; ".join(bits) + ".")
        elif status == "gap" and not rationale:
            rationale.append(f"No capability or skill covers {', '.join(missing) if missing else 'this requirement'}." )

        r["match_status"] = status
        r["match_score"] = score if status != "confirm" else 0.0
        r["match"] = {"evidence": evidence[:5], "people": people[:12], "people_count": len(people),
                      "technologies_have": have, "technologies_missing": missing, "rationale": " ".join(rationale),
                      "retrieval": method, "judged_by": "rules"}
    if llm.is_enabled():
        ai_judge(reqs, kb, inv, guidance, progress)
    return reqs


JUDGE_SYSTEM = ("You are the bid director of an IT services company deciding, requirement by requirement, whether the company can deliver. "
                "Judge ONLY from the evidence listed for each requirement (the company's capabilities, case studies, accelerators, certifications "
                "and people). Never assume a capability, product or certification that is not listed. Be strict but fair: a capability in the same "
                "domain with relevant people is 'partial' unless the evidence clearly covers it.")


def ai_judge(reqs: list[dict], kb: CompanyKB, inv: dict, guidance: str = "", progress=None) -> None:
    """AI decides strong / partial / gap for every technical and compliance requirement, citing evidence."""
    todo = [r for r in reqs if r["category"] != "Commercial" and r.get("subcategory") not in CONFIRM_SUBS and r["match_status"] != "confirm"]
    certs = [c["name"] for c in kb.certifications]
    batches = [todo[i:i + 18] for i in range(0, len(todo), 18)]
    for n, chunk in enumerate(batches, start=1):
        if progress:
            progress(f"AI judging capability fit: batch {n} of {len(batches)}")
        lines, allowed = [], []
        for k, r in enumerate(chunk):
            ev = [e["name"] for e in r["match"]["evidence"][:4]]
            allowed.append(set(ev) | set(certs))
            ppl = "; ".join(f"{t}: {inv[t]['people']} people (avg level {inv[t]['avg_level']})" for t in r.get("technologies", []) if t in inv) or "none listed"
            lines.append(f"[{k}] {r['text'][:420]}\n  candidate evidence: {' | '.join(ev) or 'none'}\n  people with named technologies: {ppl}\n"
                         f"  technologies not in company inventory: {', '.join(r['match']['technologies_missing']) or 'none'}")
        prompt = (f"Company certifications: {', '.join(certs) or 'none'}\n\nRequirements:\n" + "\n".join(lines) +
                  '\n\nReturn a JSON array, one object per requirement: {"i": index, "status": "strong|partial|gap", "score": 0-100, '
                  '"evidence": ["<names copied exactly from that requirement\'s candidate evidence or the certifications>"], '
                  '"rationale": "<one sentence, citing the evidence>"}' + guidance)
        try:
            res = llm.complete_json(JUDGE_SYSTEM, prompt, max_tokens=8000)
        except Exception:
            return
        if isinstance(res, dict):
            res = next((v for v in res.values() if isinstance(v, list)), [])
        for it in res if isinstance(res, list) else []:
            try:
                k = int(it["i"])
                r = chunk[k]
            except Exception:
                continue
            st = it.get("status")
            if st not in ("strong", "partial", "gap"):
                continue
            cited = [e for e in (it.get("evidence") or []) if e in allowed[k]]
            r["match_status"] = st
            try:
                r["match_score"] = round(max(0, min(100, float(it.get("score", 50)))) / 100, 2)
            except (TypeError, ValueError):
                pass
            if cited:
                order = {name: i for i, name in enumerate(cited)}
                ev = sorted(r["match"]["evidence"], key=lambda e: order.get(e["name"], 99))
                for c in cited:
                    if c in certs and not any(e["name"] == c for e in ev):
                        ev.insert(0, {"type": "Certification", "name": c, "score": 1.0})
                r["match"]["evidence"] = ev[:5]
            r["match"]["rationale"] = str(it.get("rationale") or r["match"]["rationale"])[:400]
            r["match"]["judged_by"] = "ai"


# --------------------------------------------------------------------------- gaps
METHOD_SUBS = {"Project Management", "Maintainability & Quality", "Monitoring & Operations", "Service Levels", "Transition & Knowledge Transfer",
               "Support & Incident Management", "General Scope", "Testing & QA", "Team & Experience", "Performance & Scalability", "Availability & Continuity"}
def ai_mitigations(reqs: list[dict], kb: CompanyKB, engagement_type: str = "", guidance: str = "", progress=None) -> dict[str, dict]:
    """AI proposes the best mitigation for each gap/partial requirement, grounded in what the company has."""
    todo = [r for r in reqs if r["match_status"] in ("gap", "partial") and r["category"] != "Commercial"]
    todo.sort(key=lambda r: (r["match_status"] != "gap", r.get("priority") != "Mandatory"))
    todo = todo[:54]
    if not todo:
        return {}
    inv = kb.tech_inventory()
    partners = [c["name"] for c in kb.certifications if c.get("kind") == "partner"]
    families = defaultdict(list)
    for t, v in inv.items():
        if v["people"]:
            families[K.TECH_FAMILY.get(t, "Other")].append(f"{t} ({v['people']})")
    profile = (f"Capabilities: {', '.join(c['name'] for c in kb.capabilities)}\nPartnerships: {', '.join(partners) or 'none'}\n"
               f"Company certifications: {', '.join(c['name'] for c in kb.certifications if c.get('kind') == 'company') or 'none'}\n"
               "Skills by family (people): " + "; ".join(f"{f}: {', '.join(v[:8])}" for f, v in families.items()))
    out: dict[str, dict] = {}
    batches = [todo[i:i + 18] for i in range(0, len(todo), 18)]
    for n, chunk in enumerate(batches, start=1):
        if progress:
            progress(f"AI planning mitigations: batch {n} of {len(batches)}")
        lines = [f"[{k}] ({r['match_status']}, {r.get('priority')}) {r['text'][:380]} | missing: {', '.join(r['match'].get('technologies_missing', [])) or 'n/a'}"
                 for k, r in enumerate(chunk)]
        prompt = (f"Company profile:\n{profile}\nEngagement type: {engagement_type}\n\nGaps:\n" + "\n".join(lines) +
                  '\n\nFor each gap return the single best way to close it for THIS company. JSON array: [{"i": index, '
                  '"type": "Partner|Upskill|Hire|Certify|Build|Define method", "detail": "<specific action naming the company\'s own adjacent '
                  'skills, partners or capabilities where relevant; one or two sentences>", "effort": "<duration>", "cost": "Low|Medium|High"}]' + guidance)
        try:
            res = llm.complete_json("You are a delivery director planning how an IT services firm closes capability gaps before bidding. "
                                    "Prefer realistic, specific actions. Never invent partners or certifications the company does not have; "
                                    "if a partner is needed and none is listed, say what kind of partner to find.", prompt, max_tokens=8000)
        except Exception:
            break
        if isinstance(res, dict):
            res = next((v for v in res.values() if isinstance(v, list)), [])
        for it in res if isinstance(res, list) else []:
            try:
                r = chunk[int(it["i"])]
            except Exception:
                continue
            if it.get("type") in ("Partner", "Upskill", "Hire", "Certify", "Build", "Define method") and it.get("detail"):
                out[r["code"]] = {"type": it["type"], "detail": str(it["detail"])[:500], "effort": str(it.get("effort", ""))[:40],
                                  "cost": it.get("cost") if it.get("cost") in ("Low", "Medium", "High") else "Medium", "ai": True}
    return out


def analyze_gaps(reqs: list[dict], kb: CompanyKB, engagement_type: str = "", ai_options: dict | None = None) -> dict:
    inv = kb.tech_inventory()
    company_techs = set(inv)
    families_have = defaultdict(list)
    for t in company_techs:
        if t in K.TECH_FAMILY:
            families_have[K.TECH_FAMILY[t]].append(t)

    gap_items = []
    missing_counter: dict[str, list[str]] = defaultdict(list)
    for r in reqs:
        if r["match_status"] not in ("gap", "partial"):
            r["gap"] = {}
            continue
        missing = r["match"].get("technologies_missing", [])
        options = []
        for t in missing:
            missing_counter[t].append(r["code"])
        for t in missing[:3]:
            fam = K.TECH_FAMILY.get(t)
            if t.startswith("ISO "):
                options.append({"type": "Certify", "detail": f"Start {t} certification (typically 6–9 months); in the meantime, propose a partner that holds it or confirm whether it is mandatory for award.",
                                "effort": "6–9 months", "cost": "Medium"})
            elif t in K.PARTNER_PRODUCTS or engagement_type == "product" and fam == "Fraud & identity intelligence":
                options.append({"type": "Partner", "detail": f"Partner with a specialist {t} product vendor and lead integration, deployment and support as the system integrator.",
                                "effort": "2–4 weeks to agree terms", "cost": "Revenue share / resale margin"})
            elif fam and families_have.get(fam):
                near = ", ".join(sorted(families_have[fam])[:3])
                options.append({"type": "Upskill", "detail": f"Cross-train engineers already skilled in {near} on {t}; add a short certification sprint.",
                                "effort": "3–6 weeks", "cost": "Low"})
            else:
                options.append({"type": "Hire", "detail": f"Hire or contract specialists in {t} for the delivery window.",
                                "effort": "4–8 weeks", "cost": "Medium"})
        method_like = r.get("subcategory") in METHOD_SUBS
        if not missing and method_like and r["match_status"] == "gap":
            options.append({"type": "Define method", "detail": "Nothing in the library evidences this yet: write the delivery method (owner, tooling, cadence) "
                            "into the response, and add it to your capability library so future bids match it.", "effort": "1–2 days", "cost": "Low"})
        elif not missing:
            if r["match_status"] == "gap":
                options.append({"type": "Build", "detail": "No direct capability: design a solution component and validate it with an architect before committing.",
                                "effort": "Depends on scope", "cost": "Medium"})
            else:
                options.append({"type": "Strengthen evidence", "detail": "Capability exists but evidence is thin: add a reference project, demo or named expert to the response.",
                                "effort": "Days", "cost": "Low"})
        if ai_options and r["code"] in ai_options:
            ao = ai_options[r["code"]]
            options = [ao] + [o for o in options if o["type"] != ao["type"]][:2]
        risk = "Medium" if (method_like and not missing and r["match_status"] == "gap") else \
            "High" if r["match_status"] == "gap" and r.get("priority") == "Mandatory" else "Medium" if r["match_status"] == "gap" or r.get("priority") == "Mandatory" else "Low"
        r["gap"] = {"risk": risk, "options": options, "recommended": options[0]["type"] if options else ""}
        gap_items.append(r)

    mand = [r for r in reqs if r.get("priority") == "Mandatory" and r["match_status"] in ("strong", "partial", "gap")]
    if mand:
        coverage = sum(1.0 if r["match_status"] == "strong" else 0.7 if r["match_status"] == "partial" else 0 for r in mand) / len(mand)
    else:
        coverage = 0.0
    high = sum(1 for r in gap_items if r["gap"]["risk"] == "High")
    readiness = round(coverage * 100 - min(15, high * 1.5))
    # Readiness once the recommended mitigations (partner, upskill, hire, certify) are in place.
    credit = {"Partner": 0.75, "Upskill": 0.7, "Strengthen evidence": 0.9, "Define method": 0.85, "Hire": 0.55, "Build": 0.5, "Certify": 0.4}
    if mand:
        mitigated = sum(1.0 if r["match_status"] == "strong" else max(0.7, credit.get(r["gap"].get("recommended", ""), 0.5)) if r["match_status"] == "partial"
                        else credit.get(r["gap"].get("recommended", ""), 0.3) for r in mand) / len(mand)
    else:
        mitigated = 0.0
    mitigated_readiness = round(mitigated * 100)
    partner_led = sum(1 for r in gap_items if r["gap"].get("recommended") == "Partner")
    if readiness >= 70:
        verdict = "Bid"
    elif mitigated_readiness >= 70:
        verdict = "Bid with partners" if partner_led >= 3 else "Bid with mitigations"
    elif mitigated_readiness >= 55:
        verdict = "Qualify carefully"
    else:
        verdict = "No bid"
    top_missing = sorted(({"technology": t, "requirements": len(v), "codes": v[:8],
                           "recommendation": ("Partner" if t in K.PARTNER_PRODUCTS else "Certify" if t.startswith("ISO ")
                                              else "Upskill" if families_have.get(K.TECH_FAMILY.get(t, "")) else "Hire")}
                          for t, v in missing_counter.items()), key=lambda x: -x["requirements"])
    counts = defaultdict(int)
    for r in reqs:
        counts[r["match_status"]] += 1
    return {"coverage_pct": round(coverage * 100), "readiness": max(0, readiness), "mitigated_readiness": mitigated_readiness,
            "verdict": verdict, "partner_led": partner_led, "counts": dict(counts),
            "high_risk": high, "top_missing": top_missing[:12],
            "risk_counts": {k: sum(1 for r in gap_items if r["gap"]["risk"] == k) for k in ("High", "Medium", "Low")}}
