import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight, Check } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import UploadReview, { KIND_INFO, TemplateUpload } from "../components/UploadReview";
import { PageLoader, ProductMark, Spinner, useToast } from "../components/ui";
import { api } from "../lib/api";

const STEPS = [
  { key: "profile", title: "Company profile" },
  { key: "capabilities", title: "Capabilities" },
  { key: "skills", title: "Skills matrix" },
  { key: "certifications", title: "Certifications" },
  { key: "rates", title: "Rate card" },
  { key: "case_studies", title: "Case studies" },
  { key: "template", title: "Proposal template" },
];

function Profile({ company, onSaved }: { company: any; onSaved: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [f, setF] = useState({ name: company.name, industry: company.industry, website: company.website, headquarters: company.headquarters,
    headcount: company.headcount || "", founded: company.founded, currency: company.currency || "USD", about: company.about });
  const save = useMutation({
    mutationFn: () => api.put("/company", f),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["company"] }); toast("ok", "Profile saved."); onSaved(); },
    onError: (e: any) => toast("error", e.message),
  });
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <p className="text-ink-soft text-[14.5px]">Used in proposal boilerplate (“About us”) and to judge industry fit.</p>
      <div className="grid sm:grid-cols-2 gap-4">
        <div><label className="label">Company name</label><input className="input" value={f.name} onChange={set("name")} required /></div>
        <div><label className="label">Industry</label><input className="input" value={f.industry} onChange={set("industry")} placeholder="e.g. IT services – integration" required /></div>
        <div><label className="label">Headquarters</label><input className="input" value={f.headquarters} onChange={set("headquarters")} /></div>
        <div><label className="label">Website</label><input className="input" value={f.website} onChange={set("website")} /></div>
        <div><label className="label">Headcount</label><input className="input num" type="number" value={f.headcount} onChange={set("headcount")} /></div>
        <div><label className="label">Rate card currency</label>
          <select className="input" value={f.currency} onChange={set("currency")}>{["USD", "INR", "AED", "EUR", "GBP", "SAR", "KWD"].map((c) => <option key={c}>{c}</option>)}</select>
        </div>
      </div>
      <div>
        <label className="label">About the company</label>
        <textarea className="input h-28 py-2" value={f.about} onChange={set("about")} required placeholder="Two or three sentences a client would read in a proposal." />
      </div>
      <button className="btn-primary" disabled={save.isPending}>{save.isPending && <Spinner />} Save and continue</button>
    </form>
  );
}

export default function Onboarding() {
  const nav = useNavigate();
  const { data: company, isLoading } = useQuery({ queryKey: ["company"], queryFn: () => api.get("/company") });
  const [step, setStep] = useState<string | null>(null);
  useEffect(() => {
    if (company && step === null) {
      const first = STEPS.find((s) => !company.onboarding.steps[s.key]);
      setStep(first?.key || "profile");
    }
  }, [company, step]);
  if (isLoading || !company || !step) return <PageLoader />;
  const steps = company.onboarding.steps;
  const idx = STEPS.findIndex((s) => s.key === step);
  const next = () => (idx < STEPS.length - 1 ? setStep(STEPS[idx + 1].key) : nav("/app"));
  const cur = STEPS[idx];
  const required = company.onboarding.required as string[];

  return (
    <div className="min-h-screen bg-paper">
      <header className="h-16 bg-white border-b border-line flex items-center px-4 md:px-8">
        <ProductMark />
        <div className="flex-1" />
        <Link to="/app" className="btn-ghost">Go to workspace</Link>
      </header>
      <div className="max-w-6xl mx-auto px-4 md:px-8 py-8 grid md:grid-cols-[240px_1fr] gap-8">
        <aside>
          <div className="text-[13px] font-semibold text-ink-muted mb-3">Set up {company.name}</div>
          <ol className="space-y-1">
            {STEPS.map((s, i) => (
              <li key={s.key}>
                <button
                  onClick={() => setStep(s.key)}
                  className={clsx("w-full flex items-center gap-3 rounded-md px-2.5 h-10 text-left text-[14px]", s.key === step ? "bg-white shadow-card font-semibold" : "hover:bg-white/60")}
                >
                  <span className={clsx("h-6 w-6 rounded-full grid place-items-center text-[11px] font-bold shrink-0",
                    steps[s.key] ? "bg-ok text-white" : s.key === step ? "bg-brand-500 text-white" : "bg-line text-ink-muted")}>
                    {steps[s.key] ? <Check className="h-3.5 w-3.5" /> : i + 1}
                  </span>
                  <span className="flex-1">{s.title}</span>
                  {required.includes(s.key) && !steps[s.key] && <span className="text-[10.5px] text-ember-600 font-semibold">Required</span>}
                </button>
              </li>
            ))}
          </ol>
          <div className="mt-6 text-[12.5px] text-ink-muted leading-relaxed">
            Everything you upload stays in your workspace and builds your private knowledge graph. You can update any of it later from the Knowledge library.
          </div>
        </aside>
        <section className="card p-6 md:p-8 min-w-0">
          <div className="text-[12.5px] text-ink-muted num">Step {idx + 1} of {STEPS.length}</div>
          <h1 className="font-display text-[32px] leading-tight text-brand-950 mt-1 mb-4">{cur.key === "profile" ? "Tell us about your company" : cur.key === "template" ? "Your proposal template" : KIND_INFO[cur.key].title}</h1>
          {cur.key === "profile" ? (
            <Profile company={company} onSaved={next} />
          ) : cur.key === "template" ? (
            <TemplateUpload />
          ) : (
            <UploadReview key={cur.key} kind={cur.key} />
          )}
          {cur.key !== "profile" && (
            <div className="mt-8 pt-5 border-t border-line-soft flex items-center gap-3">
              {steps[cur.key] && <span className="text-[13px] text-ok font-semibold flex items-center gap-1.5"><Check className="h-4 w-4" /> {company.onboarding.counts[cur.key] ?? ""} in your library</span>}
              <div className="flex-1" />
              {idx === STEPS.length - 1 ? (
                <button className="btn-ember" onClick={() => nav("/app/deals?new=1")}>Start your first deal <ArrowRight className="h-4 w-4" /></button>
              ) : (
                <button className="btn-outline" onClick={next}>{steps[cur.key] || !required.includes(cur.key) ? "Next" : "Skip for now"} <ArrowRight className="h-4 w-4" /></button>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
