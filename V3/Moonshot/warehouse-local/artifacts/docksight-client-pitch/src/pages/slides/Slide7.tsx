const base = import.meta.env.BASE_URL;
export default function Slide7() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <h1 className="ey-title">From exception to a traceable decision.</h1>
    <div className="ey-content ey-columns ey-copy">
      <p className="ey-column">Inspect the issue and affected work</p>
      <p className="ey-column">Take the permitted action with supporting evidence</p>
      <p className="ey-column">Verify the resulting state and retain action history</p>
    </div>
    <p className="ey-note">Stale edits are rejected—not silently overwritten</p>
    <p className="ey-footer">07</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="ey-logo" />
  </div>;
}