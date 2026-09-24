const base = import.meta.env.BASE_URL;
export default function Slide8() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <h1 className="ey-title">Metrics Dashboard</h1>
    <p className="absolute left-[4.75vw] top-[17vh] text-[1.5vw] text-muted">All facilities · Demo comparison — illustrative results</p>
    <table className="absolute left-[4.75vw] top-[25vh] w-[90.5vw] text-[2vw] text-left border-collapse">
      <thead className="text-primary border-b-[0.15vw] border-primary">
        <tr><th className="pb-[2vh] w-[45%] font-normal">Metric</th><th className="pb-[2vh] font-normal">Baseline</th><th className="pb-[2vh] font-normal">Current</th><th className="pb-[2vh] font-normal">Difference</th></tr>
      </thead>
      <tbody>
        <tr className="border-b border-white/20"><td className="py-[2vh]">Order cycle time</td><td>11.31 h</td><td className="text-primary">7.38 h</td><td>↓ 3.93 h</td></tr>
        <tr className="border-b border-white/20"><td className="py-[2vh]">On-time carrier departure</td><td>21.8%</td><td className="text-primary">97.0%</td><td>↑ 75.2 pp</td></tr>
        <tr className="border-b border-white/20"><td className="py-[2vh]">Inventory accuracy</td><td>21.1%</td><td className="text-primary">99.0%</td><td>↑ 77.9 pp</td></tr>
        <tr className="border-b border-white/20"><td className="py-[2vh]">False availability rate</td><td>4.9%</td><td className="text-primary">0.3%</td><td>↓ 4.6 pp</td></tr>
        <tr className="border-b border-white/20"><td className="py-[2vh]">Human interventions (proxy)<span className="block text-[1.5vw] text-muted mt-[0.5vh]">Per 1,000 robot tasks</span></td><td>369.05</td><td className="text-primary">34.63</td><td>↓ 334.42</td></tr>
      </tbody>
    </table>
    <p className="absolute left-[4.75vw] right-[7vw] bottom-[10vh] text-[1.5vw] leading-[1.3] text-muted">August 2026 baseline vs September full-month scenario—not observed client outcomes.<br />pp = percentage points · Dashboard snapshot: 22 September 2026</p>
    <p className="ey-footer">08</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="ey-logo" />
  </div>;
}