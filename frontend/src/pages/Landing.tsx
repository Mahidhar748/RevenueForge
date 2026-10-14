import clsx from "clsx";
import { ArrowRight, EyeOff, FileSearch, Lock, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ProductMark } from "../components/ui";
import { CoverageMap, FitLegend, PriceLadder, ReadinessScale } from "../components/viz";
import { useAuth } from "../lib/auth";
import { STAGES } from "../lib/format";

// The hero shows the product's core move: lines of an RFP become classified, traceable requirements.
const RFP_LINES = [
  { t: "4.2 Scope and Technical Requirements", h: true },
  { t: "The bidder shall expose core services through secured REST APIs with OAuth 2.0.", cat: "Functional", page: 6 },
  { t: "The solution must integrate with the existing CRM and ERP platforms in real time.", cat: "Functional", page: 7 },
  { t: "Availability of 99.9% with disaster recovery in a second region.", cat: "Non-functional", page: 9 },
  { t: "The bidder shall hold a current ISO/IEC 27001 certification.", cat: "Compliance", page: 14 },
  { t: "Payment will be made against accepted milestones, net 45 days.", cat: "Commercial", page: 18 },
];
const CAT_COLOR: Record<string, string> = {
  Functional: "bg-brand-50 text-brand-700 border-brand-200",
  "Non-functional": "bg-[#EEF0FB] text-[#4A54A8] border-[#D5D9F4]",
  Compliance: "bg-[#F3ECF8] text-[#7A3E9A] border-[#E3D2EE]",
  Commercial: "bg-ember-50 text-ember-600 border-ember-100",
};
const MATCH = ["Strong · API Management", "Strong · 12 engineers", "Partial · Cloud Operations", "Gap · ISO 27001 → certify", "Confirm · finance"];

function HeroVisual() {
  const [n, setN] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setN(RFP_LINES.length);
      return;
    }
    const id = setInterval(() => setN((x) => (x >= RFP_LINES.length ? x : x + 1)), 650);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="grid md:grid-cols-[1.15fr_1fr] gap-4 md:gap-5 items-stretch text-left">
      <div className="rounded-xl bg-white shadow-lift border border-line p-5 md:p-7 flex flex-col">
        <div className="flex items-center justify-between gap-4 text-[11.5px] text-ink-faint mb-4">
          <span className="truncate">Sample RFP · Digital Platform Programme</span>
          <span className="num shrink-0">p. 6 of 30</span>
        </div>
        <div className="doc-text text-[14.5px] leading-relaxed space-y-2">
          {RFP_LINES.map((l, i) =>
            l.h ? (
              <div key={i} className="font-sans font-bold text-[13.5px] text-ink pb-1">{l.t}</div>
            ) : (
              <p key={i} className={clsx("rounded px-1.5 py-0.5 -mx-1.5 transition-colors duration-500", i <= n && "bg-[#FFF1D6]")}>{l.t}</p>
            ),
          )}
        </div>
        <div className="mt-auto pt-5 flex items-center gap-2 text-[12px] text-ink-muted border-t border-line-soft">
          <span className="h-2 w-2 rounded-full bg-ok" />
          {Math.min(n, RFP_LINES.length - 1)} of {RFP_LINES.length - 1} requirements found on this page
        </div>
      </div>
      <div className="flex flex-col gap-2.5">
        <div className="text-[11.5px] font-semibold uppercase tracking-wider text-ink-faint px-1 pt-1">Extracted and matched</div>
        {RFP_LINES.slice(1).map((l, i) => (
          <div
            key={i}
            className={clsx(
              "flex-1 rounded-lg border border-line bg-white px-4 py-2.5 shadow-card transition-all duration-500 flex flex-col justify-center",
              i + 1 <= n ? "opacity-100 translate-y-0" : "opacity-0 translate-y-1",
            )}
          >
            <div className="flex items-center gap-2 text-[11px]">
              <span className="num font-bold text-ink-muted">REQ-{String(i + 41).padStart(3, "0")}</span>
              <span className={clsx("chip border", CAT_COLOR[l.cat!])}>{l.cat}</span>
              <span className="ml-auto text-ink-faint num">p.{l.page}</span>
            </div>
            <div className="text-[13px] text-ink-soft mt-1 truncate">{MATCH[i]}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// A fixed, invented sample bid for the "whole bid on one screen" section.
const SAMPLE_SECTIONS: [string, string][] = [
  ["3.1 Integration and APIs", "SSPPGSCSPG"], ["3.2 Real-time events", "GPPSCG"], ["3.3 Data and analytics", "PSPC"],
  ["4. Non-functional", "SSPGSPSPGS"], ["5. Security and compliance", "SCSSGPSS"], ["6. Managed services", "PPSSPSPSS"],
  ["7. Project delivery", "CPSC"], ["8. Deliverables", "SPPGSP"], ["9. Commercial terms", "CCCCC"],
];
const SAMPLE_REQS = SAMPLE_SECTIONS.flatMap(([sec, code], si) => code.split("").map((c, i) => ({
  id: `${si}-${i}`, section: sec, block_idx: si * 20 + i, code: `REQ-${String(si * 12 + i + 1).padStart(3, "0")}`, page: 4 + si * 3,
  priority: (si + i) % 5 === 4 ? "Desirable" : "Mandatory", category: sec.startsWith("9") ? "Commercial" : sec.startsWith("4") ? "Non-functional" : sec.startsWith("5") ? "Compliance" : "Functional",
  match_status: { S: "strong", P: "partial", G: "gap", C: "confirm" }[c], text: `Sample requirement from section ${sec}.`,
})));

function WholeBid() {
  const counts: Record<string, number> = {};
  SAMPLE_REQS.forEach((r) => (counts[r.match_status!] = (counts[r.match_status!] || 0) + 1));
  const fmt = (v: number) => `AUD ${(v / 1e6).toFixed(2)}M`;
  return (
    <section className="bg-brand-950 text-white">
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-20">
        <h2 className="font-display text-[32px] md:text-[44px] leading-tight max-w-3xl">The whole bid on one screen.</h2>
        <p className="mt-4 text-brand-100/80 max-w-2xl text-[16px] leading-relaxed">
          Every requirement becomes one tile, coloured by whether you can deliver it today. Next to it: whether to bid, and what the price does to your margin. Decide in minutes, not after a week of spreadsheets.
        </p>
        <div className="mt-10 grid lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-4 text-ink">
          <div className="rounded-xl bg-white p-6">
            <div className="font-bold text-[15px]">Coverage map</div>
            <FitLegend counts={counts} className="mt-2 mb-4" />
            <CoverageMap reqs={SAMPLE_REQS} />
          </div>
          <div className="space-y-4">
            <div className="rounded-xl bg-white p-6">
              <div className="font-bold text-[15px]">Bid decision</div>
              <div className="font-display text-[26px] text-brand-950 mt-1 mb-5">Bid with mitigations</div>
              <ReadinessScale today={52} mitigated={81} />
            </div>
            <div className="rounded-xl bg-white p-6">
              <div className="font-bold text-[15px] mb-2">Price against cost</div>
              <PriceLadder cost={2_310_000} floorMargin={18} selected="Target" list={4_160_000} fmt={fmt}
                scenarios={[{ name: "Aggressive", price: 2_890_000, margin_pct: 20 }, { name: "Target", price: 3_210_000, margin_pct: 28 }, { name: "Premium", price: 3_610_000, margin_pct: 36 }]} />
            </div>
          </div>
        </div>
        <p className="mt-4 text-[12px] text-brand-100/60">Sample data for illustration.</p>
      </div>
    </section>
  );
}

const CHAIN = ["Requirement", "Capability", "Technology", "Skill", "Case study", "Accelerator", "Architecture", "Resource", "Cost"];

/** A pre-sales photo faded in behind the headline. Put the picture at frontend/public/hero/presales.jpg;
 * until it exists nothing is drawn, so the page never shows a broken image. */
function HeroPhoto() {
  const [ok, setOk] = useState(false);
  return (
    <div aria-hidden className={clsx("pointer-events-none absolute inset-x-0 top-0 h-[700px] transition-opacity duration-700", ok ? "opacity-100" : "opacity-0")}>
      <img
        src="/hero/presales.jpg"
        alt=""
        onLoad={() => setOk(true)}
        onError={() => setOk(false)}
        className="absolute inset-0 h-full w-full object-cover object-[center_35%] grayscale-[25%] opacity-[0.5]"
        style={{ maskImage: "linear-gradient(to bottom, #000 0%, #000 55%, transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom, #000 0%, #000 55%, transparent 100%)" }}
      />
      {/* brand tint, then a soft white glow behind the words so the headline stays easy to read */}
      <div className="absolute inset-0 bg-[#DCEEF8] mix-blend-multiply opacity-60" />
      <div className="absolute inset-0 bg-[radial-gradient(48%_52%_at_50%_44%,rgba(255,255,255,0.92)_0%,rgba(255,255,255,0.7)_55%,rgba(255,255,255,0.15)_100%)]" />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-white" />
    </div>
  );
}

export default function Landing() {
  const { user } = useAuth();
  return (
    <div className="bg-white">
      <header className="sticky top-0 z-30 px-3 md:px-6 pt-3">
        <div className="max-w-6xl mx-auto px-4 md:px-6 h-16 flex items-center gap-6 xl:gap-8 rounded-2xl bg-[#F1F3F5]/95 backdrop-blur border border-[#E3E7EA] shadow-[0_6px_20px_-12px_rgba(9,40,61,0.25)]">
          <div className="shrink-0 whitespace-nowrap"><ProductMark /></div>
          <nav className="hidden lg:flex items-center gap-6 xl:gap-7 text-[14.5px] font-semibold text-brand-950 whitespace-nowrap">
            <a href="#how" className="hover:text-brand-600">How it works</a>
            <a href="#learning" className="hover:text-brand-600">Self-learning AI</a>
            <a href="#security" className="hover:text-brand-600">Security</a>
            <a href="#compare" className="hover:text-brand-600">Why RevenueForge</a>
          </nav>
          <div className="flex-1" />
          {user ? (
            <Link to="/app" className="btn-primary rounded-full px-5 shrink-0 whitespace-nowrap">Open workspace</Link>
          ) : (
            <div className="flex items-center gap-1 shrink-0 whitespace-nowrap">
              <Link to="/login" className="h-10 px-4 inline-flex items-center rounded-full text-[14.5px] font-semibold text-brand-950 hover:bg-white">Sign in</Link>
              <Link to="/signup" className="btn-primary rounded-full px-5 hidden sm:inline-flex">Create workspace</Link>
            </div>
          )}
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[520px] bg-[radial-gradient(60%_60%_at_50%_0%,#EAF5FB_0%,rgba(255,255,255,0)_100%)]" />
        <HeroPhoto />
        <div className="relative max-w-6xl mx-auto px-4 md:px-6 pt-14 md:pt-20 text-center">
          <div className="text-[12.5px] font-semibold uppercase tracking-[0.14em] text-brand-600">AI deal &amp; proposal intelligence</div>
          <h1 className="font-doc mt-4 mx-auto max-w-[17ch] text-[42px] sm:text-[56px] lg:text-[72px] leading-[1.04] tracking-[-0.02em] font-medium text-brand-950">
            Turn an RFP into a proposal you can sign off, in hours.
          </h1>
          <p className="mt-6 mx-auto max-w-[44rem] text-[17px] md:text-[19px] leading-relaxed text-ink-soft">
            RevenueForge reads the whole document, matches every requirement to what your company has actually delivered, and drafts the
            architecture, team, price, proposal and delivery handoff. Your experts review and approve each step.
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Link to="/signup" className="btn-ember rounded-full h-12 px-7 text-[15.5px]">
              Create your company workspace <ArrowRight className="h-4 w-4" />
            </Link>
            <a href="#how" className="btn-outline rounded-full h-12 px-7 text-[15.5px] border-2 border-brand-950 text-brand-950">See how it works</a>
          </div>
        </div>
        <div className="relative max-w-5xl mx-auto px-4 md:px-6 mt-14 md:mt-16">
          <HeroVisual />
        </div>
        <div className="mt-16 bg-paper border-y border-line">
          <dl className="max-w-5xl mx-auto px-4 md:px-6 py-8 grid grid-cols-1 sm:grid-cols-3 gap-6 sm:divide-x divide-line text-center">
            {[
              ["100%", "of requirements traced to their source page"],
              ["8", "reviewable stages from RFP to delivery handoff"],
              ["0", "client names leave your workspace when masking is on"],
            ].map(([k, v]) => (
              <div key={k} className="px-4">
                <dt className="num text-[34px] font-bold text-brand-800 leading-none">{k}</dt>
                <dd className="text-[13.5px] text-ink-muted leading-snug mt-2 max-w-[16rem] mx-auto">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <WholeBid />

      <section id="how" className="scroll-mt-20">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-20">
          <h2 className="text-[28px] md:text-[38px] font-bold tracking-tight text-brand-950 text-center">One pipeline, eight reviewable steps</h2>
          <p className="mt-3 text-ink-soft max-w-2xl mx-auto text-center">Each step produces a draft the right person approves: pre-sales, solution architect, finance or delivery. Change anything and everything downstream updates.</p>
          <ol className="mt-12 grid sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-10">
            {STAGES.map((s, i) => (
              <li key={s.key} className="relative pl-12">
                <span className="absolute left-0 top-0 h-8 w-8 rounded-full bg-white border-2 border-brand-500 text-brand-700 num text-[13px] font-bold grid place-items-center">{i + 1}</span>
                <div className="font-semibold text-ink">{s.label}</div>
                <div className="text-[13.5px] text-ink-muted mt-1 leading-relaxed">{STAGE_COPY[s.key]}</div>
                <div className="text-[11.5px] text-brand-700 font-semibold mt-1.5">Approved by {s.role.toLowerCase()}</div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="learning" className="scroll-mt-20 max-w-6xl mx-auto px-4 md:px-6 py-20 grid lg:grid-cols-2 gap-12 items-center border-t border-line">
        <div>
          <h2 className="text-[28px] md:text-[34px] font-bold tracking-tight text-brand-950">It learns how your company bids</h2>
          <p className="mt-3 text-ink-soft leading-relaxed">
            Behind RevenueForge is a knowledge graph of your own company: what you can do, who can do it, where you have done it before and
            what it costs. Every correction your team makes is fed back into the AI. A classifier trains on your reviewed requirements.
            Approved answers are reused on the next RFP, and wins and actual effort calibrate future estimates. Prompts can be copied. Your deal history can't.
          </p>
        </div>
        <ol className="grid grid-cols-3 gap-2.5">
          {CHAIN.map((c, i) => (
            <li key={c} className={clsx("rounded-md border px-3 py-3 text-[14px] font-semibold", i === 0 ? "bg-brand-900 text-white border-brand-900" : "bg-white text-brand-800 border-brand-200")}>
              <span className={clsx("block text-[11px] font-medium mb-0.5", i === 0 ? "text-brand-200" : "text-ink-faint")}>{i === 0 ? "From the RFP" : i === CHAIN.length - 1 ? "To the price" : "connects to"}</span>
              {c}
            </li>
          ))}
        </ol>
      </section>

      <section id="security" className="scroll-mt-20 bg-brand-950 text-white">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-16">
          <h2 className="text-[28px] md:text-[38px] font-bold tracking-tight text-center">Built for confidential bids</h2>
          <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              [EyeOff, "Client names masked", "Turn on masking per deal and the client's name never appears in screens, AI prompts or documents."],
              [Lock, "Your workspace only", "Each company's capabilities, people, rates and RFPs are isolated. No one else can see or learn from them."],
              [FileSearch, "Every claim has a source", "Requirements link to their page in the RFP. Responses cite your real capabilities, case studies and people."],
              [ShieldCheck, "Your choice of AI", "Run on Gemini, Claude, OpenAI or Azure OpenAI. With masking on, client names never reach the AI."],
            ].map(([Icon, t, d]: any) => (
              <div key={t}>
                <Icon className="h-5 w-5 text-ember-400" />
                <div className="font-semibold mt-3">{t}</div>
                <div className="text-[13.5px] text-brand-100/80 mt-1.5 leading-relaxed">{d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="compare" className="scroll-mt-20 max-w-6xl mx-auto px-4 md:px-6 py-20">
        <h2 className="text-[28px] md:text-[34px] font-bold tracking-tight text-brand-950">Before and after</h2>
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[560px] text-[14.5px]">
            <thead>
              <tr className="text-left text-ink-muted text-[13px]">
                <th className="py-2 pr-4 font-semibold w-1/4"></th>
                <th className="py-2 pr-4 font-semibold">Today</th>
                <th className="py-2 font-semibold text-brand-700">With RevenueForge</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["RFP to first draft", "Days to weeks", "Hours"],
                ["Requirement extraction", "Manual reading and spreadsheets", "Automatic, classified, traceable to the source page"],
                ["Estimates", "Vary by author", "Grounded in your rate card, team and past deals"],
                ["Knowledge reuse", "In people's heads and old decks", "A knowledge graph that improves with every deal"],
                ["Handoff to delivery", "Context lost", "A structured pack: scope, assumptions, risks, team, plan"],
              ].map(([a, b, c]) => (
                <tr key={a} className="border-t border-line">
                  <td className="py-3 pr-4 font-semibold">{a}</td>
                  <td className="py-3 pr-4 text-ink-muted">{b}</td>
                  <td className="py-3 text-ink">{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 md:px-6 pb-20">
        <div className="rounded-xl bg-paper border border-line px-6 md:px-10 py-10 flex flex-col md:flex-row md:items-center gap-6">
          <div className="flex-1">
            <div className="text-[20px] font-bold text-brand-950">Set up your workspace in about fifteen minutes.</div>
            <div className="text-ink-soft mt-1">Upload your capabilities, skills matrix, rate card and proposal template. Then drop in your next RFP.</div>
          </div>
          <Link to="/signup" className="btn-primary rounded-full h-11 px-6 shrink-0">Create workspace</Link>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-8 flex flex-col sm:flex-row items-center gap-4 text-[13px] text-ink-muted">
          <ProductMark />
          <div className="sm:ml-auto">© {new Date().getFullYear()} RevenueForge</div>
        </div>
      </footer>
    </div>
  );
}

const STAGE_COPY: Record<string, string> = {
  requirements: "Reads the RFP, RFI, RFQ or SOW and lists every requirement, classified and linked to its page.",
  matching: "Scores each requirement against your capabilities, people, case studies and certifications.",
  gaps: "Flags what you can't cover yet, with partner, hire, upskill or certify options and a bid verdict.",
  architecture: "Drafts the solution layers and technology choices, each traced to the requirements behind it.",
  estimation: "Sizes workstreams and builds a role-wise team from your skills matrix, with named people.",
  pricing: "Applies your rate card and cost, then shows aggressive, target and premium margin scenarios.",
  proposal: "Writes the proposal and compliance matrix inside your own Word template.",
  handoff: "Hands delivery the scope, assumptions, risks, team, plan and open items.",
};
