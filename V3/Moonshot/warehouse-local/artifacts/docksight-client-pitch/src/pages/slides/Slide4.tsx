const base = import.meta.env.BASE_URL;
export default function Slide4() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <h1 className="ey-title">Put machine learning to work on maintenance review.</h1>
    <div className="ey-content grid grid-cols-[1fr_1.15fr] gap-[5vw]">
      <p className="text-[3.1vw] leading-[1.3] border-t-[0.2vw] border-primary pt-[4vh]">Estimate robot failure risk over a <strong className="text-primary">seven-day horizon</strong></p>
      <ul className="ey-list ey-copy pt-[4vh]">
        <li>Prioritize Review, Monitor and Unavailable cases</li>
        <li>Open robot signals and history for closer inspection</li>
      </ul>
    </div>
    <p className="ey-note">Experimental ML advisory—not a validated operational prediction service</p>
    <p className="ey-footer">04</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="ey-logo" />
  </div>;
}