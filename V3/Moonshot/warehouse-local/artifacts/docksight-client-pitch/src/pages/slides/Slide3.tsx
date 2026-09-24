const base = import.meta.env.BASE_URL;
export default function Slide3() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <h1 className="ey-title">One control tower. Three focused workspaces.</h1>
    <div className="ey-content ey-columns ey-copy">
      <p className="ey-column"><strong className="text-primary">Supervisors:</strong> orders, inventory and exceptions</p>
      <p className="ey-column"><strong className="text-primary">Fleet Managers:</strong> readiness, blockers and repairs</p>
      <p className="ey-column"><strong className="text-primary">Administrators:</strong> resources, configuration and audit</p>
    </div>
    <p className="ey-footer">03</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="ey-logo" />
  </div>;
}