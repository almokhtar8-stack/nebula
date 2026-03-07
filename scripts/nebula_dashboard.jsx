import { useState, useEffect, useRef } from "react";

const NAVY = "#071333";
const CREAM = "#FBF7E7";
const TEAL = "#1B8C8C";
const TEAL_LIGHT = "#24b5b5";
const GOLD = "#C9A84C";
const RED = "#C0392B";
const AMBER = "#E67E22";

const REPORT = {
  sample_id: "NEBULA_DEMO",
  generated_at: "2026-03-07",
  pipeline_version: "0.1.0",
  summary: {
    total_insights: 20,
    strong_evidence_count: 15,
    moderate_evidence_count: 5,
    referral_triggers: ["NUT-004","NUT-007","RISK-001","RISK-002","RISK-003","RISK-004","RISK-005","RISK-006"],
  },
  prs_scores: [
    { condition: "CAD", percentile: 82, label: "Coronary Artery Disease" },
    { condition: "T2D", percentile: 85, label: "Type 2 Diabetes" },
    { condition: "BrCa", percentile: 83, label: "Breast Cancer" },
    { condition: "PrCa", percentile: 4, label: "Prostate Cancer" },
  ],
  insights: {
    Fitness: [
      { id:"FIT-001", gene:"ACTN3", variant:"rs1815739", genotype:"XX", title:"Endurance Muscle Profile", text:"Your muscle fiber genetics align well with endurance activities. Alpha-actinin-3 is absent in fast-twitch fibers — a trait common in elite endurance athletes.", action:"Prioritize aerobic base training ≥3 sessions/week.", grade:"Strong", confidence:85, tier:"tier_1", referral:false },
      { id:"FIT-003", gene:"COL5A1", variant:"rs12722", genotype:"CT", title:"Soft-Tissue Injury Tendency", text:"You carry a variant associated with modestly elevated soft-tissue injury risk, particularly Achilles tendinopathy in high-impact sport.", action:"10-15 min dynamic warm-up before every session. Eccentric calf raises 3×/week.", grade:"Moderate", confidence:60, tier:"tier_1", referral:false },
      { id:"FIT-004", gene:"IL-6", variant:"rs1800795", genotype:"GG", title:"Elevated Inflammatory Response", text:"Your GG genotype produces higher IL-6 after exercise. At 5+ sessions/week, cumulative inflammation warrants deliberate recovery management.", action:"2 full rest days/week. Track resting heart rate as recovery proxy.", grade:"Moderate", confidence:70, tier:"tier_1", referral:false },
    ],
    Nutrition: [
      { id:"NUT-001", gene:"CYP1A2", variant:"rs762551", genotype:"AC", title:"Slow Caffeine Metabolizer", text:"Caffeine stays in your system significantly longer than average. At high intake, this is associated with cardiovascular risk and sleep disruption.", action:"Limit to ≤200mg/day. No caffeine after noon.", grade:"Strong", confidence:90, tier:"tier_1", referral:false },
      { id:"NUT-002", gene:"LCT", variant:"rs4988235", genotype:"TT", title:"Lactase Non-Persistence", text:"Lactase production likely decreases after childhood. GI discomfort with dairy — bloating, cramping — is genetically explained.", action:"Trial 2 weeks dairy-free. Reintroduce with lactase enzyme. Fermented dairy often tolerated.", grade:"Strong", confidence:90, tier:"tier_1", referral:false },
      { id:"NUT-003", gene:"MTHFR", variant:"rs1801133", genotype:"TT", title:"Reduced Folate Conversion", text:"Homozygous C677T reduces enzyme efficiency ~70%. Converting folic acid to active methylfolate is impaired.", action:"Choose methylfolate (5-MTHF), not folic acid. Leafy greens, lentils daily.", grade:"Strong", confidence:80, tier:"tier_1", referral:false },
      { id:"NUT-004", gene:"ALDH2", variant:"rs671", genotype:"AA", title:"Alcohol Metabolism Deficiency", text:"Near-complete loss of acetaldehyde clearance. AA homozygotes face well-documented elevated oesophageal cancer risk with alcohol exposure.", action:"Avoidance of alcohol strongly recommended. Discuss with physician.", grade:"Strong", confidence:85, tier:"tier_2", referral:true },
      { id:"NUT-005", gene:"FTO", variant:"rs9939609", genotype:"AA", title:"Appetite Regulation Variant", text:"The most replicated common obesity-associated variant. Linked to ~1.5kg higher body weight on average through appetite and satiety signalling differences.", action:"Mindful eating strategies. High-protein, high-fibre meals for satiety.", grade:"Strong", confidence:70, tier:"tier_1", referral:false },
      { id:"NUT-006", gene:"FADS1", variant:"rs174546", genotype:"TT", title:"Reduced Omega-3 Conversion", text:"Reduced delta-5 desaturase activity — plant ALA converts poorly to EPA/DHA. Circulating omega-3 levels are likely lower.", action:"Fatty fish 2-3×/week OR algae-based DHA/EPA supplement 500-1000mg/day.", grade:"Strong", confidence:80, tier:"tier_1", referral:false },
      { id:"NUT-007", gene:"HFE", variant:"rs1800562", genotype:"AA", title:"Hereditary Haemochromatosis Risk", text:"C282Y homozygosity — primary genetic risk factor for iron overload. ~28% of C282Y homozygotes develop clinical disease.", action:"Request serum ferritin + transferrin saturation annually. Avoid supplemental iron.", grade:"Strong", confidence:85, tier:"tier_2", referral:true },
      { id:"NUT-008", gene:"GC/CYP2R1/DHCR7", variant:"3 loci", genotype:"Risk ×4", title:"Vitamin D Insufficiency Risk", text:"Multiple variants associated with lower circulating 25(OH)D. Combined with limited sun exposure, supplementation is likely beneficial.", action:"Request 25(OH)D blood test. 1000-2000 IU D3/day if below 50 nmol/L.", grade:"Strong", confidence:85, tier:"tier_1", referral:false },
    ],
    "Recovery/Sleep": [
      { id:"REC-001", gene:"PER2/CLOCK", variant:"rs2304672 / rs1801260", genotype:"Evening", title:"Chronotype–Schedule Mismatch", text:"Genetic tendency toward eveningness conflicts with an early-wake schedule. Social jet lag pattern — associated with poorer sleep quality.", action:"Bright light therapy (≥10,000 lux) within 30 min of waking. Consistent wake time 7 days/week.", grade:"Moderate", confidence:75, tier:"tier_1", referral:false },
      { id:"REC-002", gene:"ADA", variant:"rs73598374", genotype:"Asn/Asn", title:"Deep Sleep Tendency", text:"Slower adenosine clearance associated with increased slow-wave (deep) sleep. Favourable for recovery, but sleep inertia on waking may be stronger.", action:"Fixed wake time. Avoid snoozing. Bright light immediately on waking.", grade:"Moderate", confidence:55, tier:"tier_1", referral:false },
      { id:"REC-003", gene:"CYP1A2", variant:"rs762551", genotype:"AC", title:"Caffeine–Sleep Convergence", text:"Slow metabolizer + >200mg caffeine + poor sleep quality: three data points converging on one high-priority intervention.", action:"Taper caffeine to ≤200mg/day over 2-3 weeks. All intake before noon. Track sleep 4 weeks.", grade:"Strong", confidence:90, tier:"tier_1", referral:false },
    ],
    "Health Risk": [
      { id:"RISK-001", gene:"PRS", variant:"CAD", genotype:"82nd %ile", title:"Elevated CAD Polygenic Risk", text:"Inherited genetic loading for coronary artery disease is higher than ~80% of the reference population. This is one risk factor among many.", action:"Lipid panel + BP check. Mediterranean diet. Regular aerobic exercise. Annual review.", grade:"Strong", confidence:85, tier:"tier_2", referral:true },
      { id:"RISK-002", gene:"PRS", variant:"T2D", genotype:"85th %ile", title:"Elevated T2D Polygenic Risk", text:"Top 20% for type 2 diabetes genetic predisposition. T2D is one of the most preventable conditions — lifestyle has large modifiable impact.", action:"HbA1c + fasting glucose. 150 min/week aerobic activity. Reduce refined carbs.", grade:"Strong", confidence:80, tier:"tier_2", referral:true },
      { id:"RISK-003", gene:"PRS", variant:"BrCa", genotype:"83rd %ile", title:"Elevated Breast Cancer Risk", text:"Top 20% for common-variant breast cancer risk. This does not test BRCA1/BRCA2 — it captures polygenic risk from many small-effect variants.", action:"Adhere to mammography screening schedule. Discuss with physician.", grade:"Strong", confidence:85, tier:"tier_2", referral:true },
      { id:"RISK-004", gene:"SLCO1B1", variant:"rs4149056", genotype:"CC", title:"Simvastatin Myopathy Risk", text:"~17× elevated risk of muscle damage from simvastatin. CPIC Level A guideline variant — highest pharmacogenomic evidence tier.", action:"Retain in medical record. If prescribed simvastatin, discuss alternatives (rosuvastatin).", grade:"Strong", confidence:85, tier:"tier_2", referral:true },
      { id:"RISK-005", gene:"DPYD", variant:"rs3918290", genotype:"*2A het", title:"⚠ Chemotherapy Toxicity Risk", text:"DPYD *2A carrier: severe, potentially life-threatening toxicity risk with 5-FU/capecitabine chemotherapy. CPIC guideline: dose reduction or alternative required.", action:"Disclose to any oncologist before cancer treatment. Retain in permanent medical record.", grade:"Strong", confidence:90, tier:"tier_3", referral:true },
      { id:"RISK-006", gene:"HLA", variant:"DQ2.5", genotype:"Positive", title:"Coeliac Disease Predisposition", text:"HLA-DQ2.5 haplotype + reported GI symptoms. Present in ~95% of coeliac patients but only ~1% of carriers develop disease.", action:"Request tTG-IgA blood test. Do NOT start gluten-free diet before testing.", grade:"Moderate", confidence:80, tier:"tier_2", referral:true },
    ],
  },
  next_steps: [
    { action:"Genetic counsellor review required before report release", reason:"DPYD Tier 3 finding (RISK-005)", urgency:"urgent" },
    { action:"Discuss report with physician", reason:"Multiple physician referral triggers present", urgency:"recommended" },
    { action:"Request lipid panel and blood pressure check", reason:"CAD PRS at 82nd percentile", urgency:"recommended" },
    { action:"Request HbA1c and fasting glucose", reason:"T2D PRS at 85th percentile", urgency:"recommended" },
    { action:"Mammography screening adherence", reason:"Breast cancer PRS at 83rd percentile", urgency:"recommended" },
    { action:"Request 25(OH)D (vitamin D) blood test", reason:"Multiple vitamin D risk alleles + low sun exposure", urgency:"routine" },
    { action:"Request serum ferritin + transferrin saturation", reason:"HFE C282Y homozygosity", urgency:"recommended" },
    { action:"Re-submit questionnaire in 6 months", reason:"Lifestyle data is time-sensitive", urgency:"routine" },
  ],
};

const CATEGORIES = ["Overview", "Fitness", "Nutrition", "Recovery/Sleep", "Health Risk", "PRS", "Next Steps"];

const tierColor = (tier) => {
  if (tier === "tier_3") return RED;
  if (tier === "tier_2") return AMBER;
  return TEAL;
};
const tierLabel = (tier) => {
  if (tier === "tier_3") return "CLINICAL";
  if (tier === "tier_2") return "PHYSICIAN";
  return "WELLNESS";
};
const gradeColor = (g) => g === "Strong" ? TEAL : g === "Moderate" ? GOLD : "#888";

function AnimatedNumber({ value, duration = 1200 }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    let start = 0;
    const step = value / (duration / 16);
    const timer = setInterval(() => {
      start += step;
      if (start >= value) { setDisplay(value); clearInterval(timer); }
      else setDisplay(Math.floor(start));
    }, 16);
    return () => clearInterval(timer);
  }, [value, duration]);
  return <span>{display}</span>;
}

function PRSBar({ score }) {
  const [animated, setAnimated] = useState(false);
  useEffect(() => { setTimeout(() => setAnimated(true), 300); }, []);
  const pct = score.percentile;
  const barColor = pct >= 80 ? RED : pct >= 60 ? AMBER : pct >= 40 ? GOLD : TEAL;
  const riskLabel = pct >= 80 ? "ELEVATED" : pct >= 60 ? "ABOVE AVG" : pct >= 40 ? "BELOW AVG" : "LOW RISK";

  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom: 8 }}>
        <div>
          <span style={{ fontFamily:"'Georgia', serif", fontSize:15, color: CREAM, fontWeight:700, letterSpacing:2 }}>{score.condition}</span>
          <span style={{ fontSize:11, color:"#aaa", marginLeft:10, letterSpacing:1 }}>{score.label}</span>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          <span style={{ fontSize:11, color: barColor, fontWeight:700, letterSpacing:2, border:`1px solid ${barColor}`, padding:"2px 8px", borderRadius:2 }}>{riskLabel}</span>
          <span style={{ fontFamily:"'Georgia', serif", fontSize:20, color: barColor, fontWeight:700 }}>{score.percentile}<span style={{fontSize:12}}>th</span></span>
        </div>
      </div>
      <div style={{ height: 6, background:"rgba(255,255,255,0.08)", borderRadius: 3, overflow:"hidden", position:"relative" }}>
        <div style={{
          position:"absolute", left:0, top:0, height:"100%",
          width: animated ? `${pct}%` : "0%",
          background: `linear-gradient(90deg, ${TEAL}, ${barColor})`,
          borderRadius: 3,
          transition: "width 1.2s cubic-bezier(0.16,1,0.3,1)",
          boxShadow: `0 0 12px ${barColor}55`
        }}/>
        <div style={{
          position:"absolute", top:-3, height:12, width:2, background: CREAM,
          left: animated ? `${pct}%` : "0%",
          transition: "left 1.2s cubic-bezier(0.16,1,0.3,1)",
          borderRadius:1, boxShadow:`0 0 6px ${CREAM}`
        }}/>
      </div>
      <div style={{ display:"flex", justifyContent:"space-between", marginTop:4 }}>
        {["0th","25th","50th","75th","100th"].map(l => (
          <span key={l} style={{ fontSize:9, color:"#555", letterSpacing:1 }}>{l}</span>
        ))}
      </div>
    </div>
  );
}

function InsightCard({ r, i }) {
  const [open, setOpen] = useState(false);
  const tc = tierColor(r.tier);
  return (
    <div
      onClick={() => setOpen(o => !o)}
      style={{
        border: `1px solid ${open ? tc : "rgba(255,255,255,0.08)"}`,
        borderRadius: 8,
        padding: "16px 20px",
        marginBottom: 10,
        cursor:"pointer",
        background: open ? `${tc}0d` : "rgba(255,255,255,0.02)",
        transition:"all 0.25s ease",
        animation:`slideIn 0.4s ease ${i*0.06}s both`,
      }}
    >
      <div style={{ display:"flex", alignItems:"center", gap:12, justifyContent:"space-between" }}>
        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <span style={{ fontSize:10, fontWeight:700, letterSpacing:2, color: tc, border:`1px solid ${tc}`, padding:"2px 7px", borderRadius:2, whiteSpace:"nowrap" }}>
            {tierLabel(r.tier)}
          </span>
          <div>
            <div style={{ fontSize:13, fontWeight:700, color: CREAM, letterSpacing:0.5 }}>{r.title}</div>
            <div style={{ fontSize:10, color:"#777", letterSpacing:1, marginTop:2 }}>
              {r.gene} · {r.variant} · <span style={{color: gradeColor(r.grade)}}>{r.grade}</span> · {r.confidence}% confidence
            </div>
          </div>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <span style={{ fontSize:11, fontFamily:"monospace", color:"#555", background:"rgba(0,0,0,0.3)", padding:"3px 8px", borderRadius:4 }}>{r.genotype}</span>
          <span style={{ color:"#555", fontSize:16, transition:"transform 0.2s", transform: open ? "rotate(180deg)" : "none" }}>›</span>
        </div>
      </div>

      {open && (
        <div style={{ marginTop:14, paddingTop:14, borderTop:"1px solid rgba(255,255,255,0.06)" }}>
          <p style={{ fontSize:12, color:"#bbb", lineHeight:1.7, margin:"0 0 10px" }}>{r.text}</p>
          <div style={{ background:"rgba(27,140,140,0.1)", border:`1px solid ${TEAL}33`, borderRadius:6, padding:"10px 14px" }}>
            <div style={{ fontSize:10, letterSpacing:2, color: TEAL, marginBottom:4, fontWeight:700 }}>WHAT TO DO</div>
            <div style={{ fontSize:12, color: CREAM, lineHeight:1.6 }}>{r.action}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function NextStepRow({ step, i }) {
  const colors = { urgent: RED, recommended: AMBER, routine: TEAL };
  const c = colors[step.urgency] || TEAL;
  return (
    <div style={{
      display:"flex", gap:14, alignItems:"flex-start",
      padding:"14px 0", borderBottom:"1px solid rgba(255,255,255,0.05)",
      animation:`slideIn 0.4s ease ${i*0.07}s both`
    }}>
      <div style={{ width:8, height:8, borderRadius:"50%", background:c, marginTop:4, flexShrink:0, boxShadow:`0 0 8px ${c}` }}/>
      <div>
        <div style={{ fontSize:13, color: CREAM, fontWeight:600 }}>{step.action}</div>
        <div style={{ fontSize:11, color:"#666", marginTop:3 }}>{step.reason}</div>
      </div>
      <span style={{ marginLeft:"auto", fontSize:9, letterSpacing:2, color:c, border:`1px solid ${c}33`, padding:"2px 8px", borderRadius:2, whiteSpace:"nowrap", flexShrink:0 }}>
        {step.urgency.toUpperCase()}
      </span>
    </div>
  );
}

function Overview() {
  const all = Object.values(REPORT.insights).flat();
  const cats = Object.entries(REPORT.insights).map(([k,v])=>({name:k,count:v.length}));
  const maxCount = Math.max(...cats.map(c=>c.count));
  return (
    <div>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:16, marginBottom:32 }}>
        {[
          {label:"Total Insights", value:20, color: TEAL},
          {label:"Strong Evidence", value:15, color: TEAL},
          {label:"Physician Flags", value:8, color: AMBER},
          {label:"Clinical Alerts", value:1, color: RED},
        ].map((s,i) => (
          <div key={i} style={{
            background:"rgba(255,255,255,0.03)", border:`1px solid rgba(255,255,255,0.08)`,
            borderRadius:8, padding:"20px 16px", textAlign:"center",
            animation:`slideIn 0.4s ease ${i*0.1}s both`
          }}>
            <div style={{ fontFamily:"'Georgia',serif", fontSize:40, fontWeight:700, color:s.color, lineHeight:1 }}>
              <AnimatedNumber value={s.value} duration={1000+i*200}/>
            </div>
            <div style={{ fontSize:10, color:"#666", letterSpacing:2, marginTop:8 }}>{s.label}</div>
          </div>
        ))}
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16 }}>
        <div style={{ background:"rgba(255,255,255,0.02)", border:"1px solid rgba(255,255,255,0.06)", borderRadius:8, padding:20 }}>
          <div style={{ fontSize:10, letterSpacing:3, color:"#555", marginBottom:16, fontWeight:700 }}>FINDINGS BY CATEGORY</div>
          {cats.map((c,i) => (
            <div key={i} style={{ marginBottom:12 }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:5 }}>
                <span style={{ fontSize:12, color:"#aaa" }}>{c.name}</span>
                <span style={{ fontSize:12, color: TEAL, fontWeight:700 }}>{c.count}</span>
              </div>
              <div style={{ height:4, background:"rgba(255,255,255,0.05)", borderRadius:2, overflow:"hidden" }}>
                <div style={{
                  height:"100%", borderRadius:2,
                  background:`linear-gradient(90deg, ${TEAL}, ${TEAL_LIGHT})`,
                  width:`${(c.count/maxCount)*100}%`,
                  boxShadow:`0 0 8px ${TEAL}66`,
                  transition:"width 1s ease"
                }}/>
              </div>
            </div>
          ))}
        </div>

        <div style={{ background:"rgba(255,255,255,0.02)", border:"1px solid rgba(255,255,255,0.06)", borderRadius:8, padding:20 }}>
          <div style={{ fontSize:10, letterSpacing:3, color:"#555", marginBottom:16, fontWeight:700 }}>TOP FINDINGS</div>
          {all.filter(r=>r.confidence>=85).slice(0,4).map((r,i)=>(
            <div key={i} style={{ display:"flex", alignItems:"center", gap:10, marginBottom:12 }}>
              <div style={{ width:32, height:32, borderRadius:"50%", background:`${tierColor(r.tier)}22`, border:`1px solid ${tierColor(r.tier)}55`, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
                <span style={{ fontSize:10, fontWeight:700, color:tierColor(r.tier) }}>{r.confidence}</span>
              </div>
              <div>
                <div style={{ fontSize:12, color: CREAM, fontWeight:600 }}>{r.title}</div>
                <div style={{ fontSize:10, color:"#555" }}>{r.id} · {r.grade}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function NebulaApp() {
  const [tab, setTab] = useState("Overview");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { setTimeout(() => setLoaded(true), 100); }, []);

  const insights = CATEGORIES.includes(tab) && tab !== "Overview" && tab !== "PRS" && tab !== "Next Steps"
    ? REPORT.insights[tab] || []
    : [];

  return (
    <div style={{
      background: NAVY, minHeight:"100vh", fontFamily:"'Helvetica Neue', Helvetica, sans-serif",
      color: CREAM, opacity: loaded ? 1 : 0, transition:"opacity 0.5s ease"
    }}>
      <style>{`
        @keyframes slideIn { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
        ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-track{background:#0a1630} ::-webkit-scrollbar-thumb{background:${TEAL}44;border-radius:2px}
        * { box-sizing:border-box; }
      `}</style>

      {/* Header */}
      <div style={{
        borderBottom:"1px solid rgba(255,255,255,0.07)",
        padding:"0 32px",
        display:"flex", alignItems:"center", justifyContent:"space-between",
        height:64, position:"sticky", top:0, zIndex:100,
        background:`${NAVY}ee`, backdropFilter:"blur(12px)"
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:16 }}>
          <div style={{
            width:36, height:36, borderRadius:"50%",
            border:`1.5px solid ${TEAL}`,
            background:`radial-gradient(circle at 40% 35%, ${TEAL}22, transparent)`,
            display:"flex", alignItems:"center", justifyContent:"center"
          }}>
            <div style={{ width:14, height:14, borderRadius:"50%", border:`1.5px solid ${TEAL}99`, position:"relative" }}>
              <div style={{ position:"absolute", top:"50%", left:"50%", transform:"translate(-50%,-50%)", width:4, height:4, borderRadius:"50%", background:TEAL }}/>
            </div>
          </div>
          <div>
            <div style={{ fontSize:15, fontWeight:800, letterSpacing:4, color:CREAM }}>NEBULA</div>
            <div style={{ fontSize:8, letterSpacing:3, color:"#555" }}>TRANSFORMING LIVES THROUGH WELLNESS</div>
          </div>
        </div>

        <div style={{ display:"flex", alignItems:"center", gap:24 }}>
          <div style={{ textAlign:"right" }}>
            <div style={{ fontSize:11, color:"#555", letterSpacing:1 }}>SAMPLE ID</div>
            <div style={{ fontSize:13, color: TEAL, fontFamily:"monospace" }}>{REPORT.sample_id}</div>
          </div>
          <div style={{ textAlign:"right" }}>
            <div style={{ fontSize:11, color:"#555", letterSpacing:1 }}>GENERATED</div>
            <div style={{ fontSize:13, color:"#aaa", fontFamily:"monospace" }}>{REPORT.generated_at}</div>
          </div>
          <div style={{
            fontSize:9, letterSpacing:2, color: AMBER, border:`1px solid ${AMBER}55`,
            padding:"4px 10px", borderRadius:2, fontWeight:700
          }}>NOT FOR CLINICAL USE</div>
        </div>
      </div>

      {/* Tab Bar */}
      <div style={{
        display:"flex", gap:0, padding:"0 32px",
        borderBottom:"1px solid rgba(255,255,255,0.06)",
        overflowX:"auto"
      }}>
        {CATEGORIES.map(c => {
          const count = REPORT.insights[c] ? REPORT.insights[c].length : null;
          const active = tab === c;
          return (
            <button key={c} onClick={() => setTab(c)} style={{
              background:"none", border:"none", cursor:"pointer",
              padding:"14px 20px", fontSize:11, letterSpacing:2,
              color: active ? TEAL : "#555",
              borderBottom: active ? `2px solid ${TEAL}` : "2px solid transparent",
              transition:"all 0.2s", whiteSpace:"nowrap",
              display:"flex", alignItems:"center", gap:6,
              fontWeight: active ? 700 : 400
            }}>
              {c.toUpperCase()}
              {count && <span style={{ background:`${TEAL}22`, color:TEAL, fontSize:9, padding:"1px 5px", borderRadius:8 }}>{count}</span>}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div style={{ padding:"28px 32px", maxWidth:960, margin:"0 auto" }}>

        {tab === "Overview" && <Overview />}

        {insights.length > 0 && (
          <div style={{ animation:"slideIn 0.4s ease" }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:20 }}>
              <div>
                <h2 style={{ margin:0, fontFamily:"'Georgia',serif", fontSize:22, color:CREAM, fontWeight:400 }}>{tab}</h2>
                <p style={{ margin:"4px 0 0", fontSize:11, color:"#555", letterSpacing:1 }}>{insights.length} FINDINGS · CLICK TO EXPAND</p>
              </div>
              <div style={{ display:"flex", gap:8 }}>
                {["Strong","Moderate"].map(g => (
                  <span key={g} style={{ fontSize:10, color:gradeColor(g), border:`1px solid ${gradeColor(g)}44`, padding:"3px 10px", borderRadius:2, letterSpacing:1 }}>
                    {insights.filter(r=>r.grade===g).length} {g.toUpperCase()}
                  </span>
                ))}
              </div>
            </div>
            {insights.map((r,i) => <InsightCard key={r.id} r={r} i={i}/>)}
          </div>
        )}

        {tab === "PRS" && (
          <div style={{ animation:"slideIn 0.4s ease" }}>
            <div style={{ marginBottom:24 }}>
              <h2 style={{ margin:"0 0 4px", fontFamily:"'Georgia',serif", fontSize:22, color:CREAM, fontWeight:400 }}>Polygenic Risk Scores</h2>
              <p style={{ margin:0, fontSize:11, color:"#555", letterSpacing:1 }}>POPULATION PERCENTILE · EUROPEAN REFERENCE (1000G)</p>
            </div>
            <div style={{ display:"flex", gap:8, marginBottom:24 }}>
              {[["LOW","≤25th",TEAL],["BELOW AVG","25–50th",GOLD],["ABOVE AVG","50–80th",AMBER],["ELEVATED","≥80th",RED]].map(([l,r,c])=>(
                <div key={l} style={{ display:"flex", alignItems:"center", gap:6 }}>
                  <div style={{ width:10, height:10, borderRadius:2, background:c }}/>
                  <span style={{ fontSize:10, color:"#777", letterSpacing:1 }}>{l} <span style={{color:"#444"}}>{r}</span></span>
                </div>
              ))}
            </div>
            <div style={{ background:"rgba(255,255,255,0.02)", border:"1px solid rgba(255,255,255,0.06)", borderRadius:8, padding:24 }}>
              {REPORT.prs_scores.map((s,i) => <PRSBar key={i} score={s}/>)}
            </div>
            <div style={{ marginTop:16, padding:"14px 18px", background:`${AMBER}0d`, border:`1px solid ${AMBER}33`, borderRadius:6 }}>
              <div style={{ fontSize:11, color:`${AMBER}cc`, lineHeight:1.6 }}>
                ⚠ PRS reflects inherited predisposition only. It is not a diagnosis. Lifestyle, clinical values, and family history are essential context. These models are optimised for European ancestry — accuracy varies for other populations.
              </div>
            </div>
          </div>
        )}

        {tab === "Next Steps" && (
          <div style={{ animation:"slideIn 0.4s ease" }}>
            <div style={{ marginBottom:24 }}>
              <h2 style={{ margin:"0 0 4px", fontFamily:"'Georgia',serif", fontSize:22, color:CREAM, fontWeight:400 }}>Recommended Actions</h2>
              <p style={{ margin:0, fontSize:11, color:"#555", letterSpacing:1 }}>{REPORT.next_steps.length} ACTIONS DERIVED FROM YOUR FINDINGS</p>
            </div>
            <div style={{ display:"flex", gap:8, marginBottom:20 }}>
              {["urgent","recommended","routine"].map(u => {
                const c = {urgent:RED,recommended:AMBER,routine:TEAL}[u];
                const count = REPORT.next_steps.filter(s=>s.urgency===u).length;
                return <span key={u} style={{ fontSize:10, color:c, border:`1px solid ${c}44`, padding:"3px 12px", borderRadius:2, letterSpacing:1 }}>{count} {u.toUpperCase()}</span>;
              })}
            </div>
            <div style={{ background:"rgba(255,255,255,0.02)", border:"1px solid rgba(255,255,255,0.06)", borderRadius:8, padding:"0 20px" }}>
              {REPORT.next_steps.map((s,i) => <NextStepRow key={i} step={s} i={i}/>)}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{ borderTop:"1px solid rgba(255,255,255,0.05)", padding:"16px 32px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
        <span style={{ fontSize:10, color:"#333", letterSpacing:1 }}>NEBULA PIPELINE v{REPORT.pipeline_version} · RULESET v0.1.0 · 51 VARIANTS · 21 RULES</span>
        <span style={{ fontSize:10, color:"#333", letterSpacing:1 }}>CONFIDENTIAL — NOT FOR CLINICAL USE</span>
      </div>
    </div>
  );
}
