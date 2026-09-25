const base = import.meta.env.BASE_URL;
export default function Slide6() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <h1 className="ey-title">See demand ahead. Understand the calculation.</h1>
    <div className="ey-content grid grid-cols-[1fr_1.15fr] gap-[5vw]">
      <p className="text-[3.1vw] leading-[1.3] border-t-[0.2vw] border-primary pt-[4vh]"><strong className="text-primary">Seven- and thirty-day</strong> SKU demand projections</p>
      <ul className="ey-list ey-copy pt-[4vh]">
        <li>Compare available stock with near-term demand</li>
        <li>Review low-stock alerts and replenishment estimates</li>
      </ul>
    </div>
    <p className="ey-note">Transparent statistical forecasting—not a trained AI model</p>
    <p className="ey-footer">06</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="ey-logo" />
  </div>;
}