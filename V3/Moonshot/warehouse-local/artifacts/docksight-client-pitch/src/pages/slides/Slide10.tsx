const base = import.meta.env.BASE_URL;
export default function Slide10() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <h1 className="ey-title">Start with the decisions that matter to your team.</h1>
    <div className="ey-content">
      <ul className="ey-list ey-copy">
        <li>Walk through a blocked order, low-stock alert and maintenance advisory</li>
        <li>Identify your highest-priority operational workflow</li>
        <li>Agree the evidence and acceptance criteria for evaluation</li>
      </ul>
    </div>
    <p className="ey-footer">10</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="ey-logo" />
  </div>;
}