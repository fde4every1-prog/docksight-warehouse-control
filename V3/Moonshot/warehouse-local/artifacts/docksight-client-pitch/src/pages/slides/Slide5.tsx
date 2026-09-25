const base = import.meta.env.BASE_URL;
export default function Slide5() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <h1 className="ey-title">Show the evidence. Keep people in control.</h1>
    <div className="ey-content">
      <ul className="ey-list ey-copy">
        <li>Review temperature, vibration, current and battery-health signals</li>
        <li>Compare recent values with historical patterns</li>
        <li>Inspect model feature importance and prediction freshness</li>
      </ul>
    </div>
    <p className="ey-note">Risk scores do not change availability or scheduling</p>
    <p className="ey-footer">05</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="ey-logo" />
  </div>;
}