const base = import.meta.env.BASE_URL;
export default function Slide1() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <img src={`${base}warehouse-cover.jpg`} crossOrigin="anonymous" alt="Warehouse operations professional reviewing work beside a mobile robot" className="absolute inset-0 w-full h-full object-cover" />
    <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(26,26,36,0.80),rgba(26,26,36,0.25))]" />
    <svg className="absolute left-[4vw] top-[19vh] w-[47vw] h-[64vh] text-primary" viewBox="0 0 600 458" fill="none" aria-hidden="true">
      <path d="M5 436V109L594 6V452H64" stroke="currentColor" strokeWidth="10.7"/>
      <path d="M0 452H11M21 452H32M43 452H54" stroke="currentColor" strokeWidth="10.7"/>
    </svg>
    <h1 className="absolute left-[8vw] top-[37vh] text-[5.3vw] leading-none font-bold">DockSight</h1>
    <p className="absolute left-[8vw] top-[51vh] w-[37vw] text-[2.3vw] leading-[1.4]">Warehouse visibility. ML-assisted maintenance review. Human-led decisions.</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="absolute right-[4vw] bottom-[8vh] w-[6.5vw] h-[12vh]" />
  </div>;
}