const base = import.meta.env.BASE_URL;
export default function Slide2() {
  return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
    <h1 className="ey-title">One warehouse. Too many disconnected decisions.</h1>
    <div className="absolute left-[4.75vw] right-[4.75vw] top-[26vh] grid grid-cols-3 gap-[3vw] text-[2.3vw] leading-[1.35]">
      <p className="border-t-[0.15vw] border-primary pt-[2.5vh]">Which orders are blocked—and why?</p>
      <p className="border-t-[0.15vw] border-primary pt-[2.5vh]">Where is stock falling short?</p>
      <p className="border-t-[0.15vw] border-primary pt-[2.5vh]">Which robots need closer review?</p>
    </div>
    <div className="absolute left-[4.75vw] right-[4.75vw] top-[48vh] flex items-center text-[2vw] font-bold text-center">
      <div className="flex-1 py-[2.8vh] bg-[#242430] border border-white/20 rounded-[0.7vw]">OMS</div>
      <div className="w-[1.7vw] h-[0.12vw] bg-muted" />
      <div className="flex-1 py-[2.8vh] bg-[#242430] border border-primary rounded-[0.7vw]">WMS</div>
      <div className="w-[1.7vw] h-[0.12vw] bg-muted" />
      <div className="flex-1 py-[2.8vh] bg-[#242430] border border-white/20 rounded-[0.7vw]">WES</div>
      <div className="w-[1.7vw] h-[0.12vw] bg-muted" />
      <div className="flex-1 py-[2.8vh] bg-[#242430] border border-primary rounded-[0.7vw]">Fleet</div>
      <div className="w-[1.7vw] h-[0.12vw] bg-muted" />
      <div className="flex-1 py-[2.8vh] bg-[#242430] border border-white/20 rounded-[0.7vw]">CMMS</div>
      <div className="w-[1.7vw] h-[0.12vw] bg-muted" />
      <div className="flex-1 py-[2.8vh] bg-[#242430] border border-white/20 rounded-[0.7vw]">Vision</div>
      <div className="w-[1.7vw] h-[0.12vw] bg-muted" />
      <div className="flex-1 py-[2.8vh] bg-[#242430] border border-primary rounded-[0.7vw]">TMS</div>
    </div>
    <div className="absolute left-[4.75vw] right-[4.75vw] top-[65vh] grid grid-cols-6 gap-[1.4vw] text-center">
      <div className="border border-primary rounded-[0.9vw] bg-[#242430] py-[2.5vh]"><p className="text-[3vw] font-bold text-primary">712</p><p className="text-[1.5vw] text-muted mt-[0.6vh]">Robots</p></div>
      <div className="border border-primary rounded-[0.9vw] bg-[#242430] py-[2.5vh]"><p className="text-[3vw] font-bold text-primary">918</p><p className="text-[1.5vw] text-muted mt-[0.6vh]">Control assets</p></div>
      <div className="border border-primary rounded-[0.9vw] bg-[#242430] py-[2.5vh]"><p className="text-[3vw] font-bold text-primary">9,360</p><p className="text-[1.5vw] text-muted mt-[0.6vh]">Inventory rows</p></div>
      <div className="border border-primary rounded-[0.9vw] bg-[#242430] py-[2.5vh]"><p className="text-[3vw] font-bold text-primary">3,500</p><p className="text-[1.5vw] text-muted mt-[0.6vh]">Orders</p></div>
      <div className="border border-primary rounded-[0.9vw] bg-[#242430] py-[2.5vh]"><p className="text-[3vw] font-bold text-primary">3,500</p><p className="text-[1.5vw] text-muted mt-[0.6vh]">Shipments</p></div>
      <div className="border border-primary rounded-[0.9vw] bg-[#242430] py-[2.5vh]"><p className="text-[3vw] font-bold text-primary">8,732</p><p className="text-[1.5vw] text-muted mt-[0.6vh]">Tasks</p></div>
    </div>
    <p className="absolute left-[4.75vw] top-[85vh] text-[1.5vw] text-muted">Ecosystem context, not live integrations · Scale snapshot from supplied reference</p>
    <p className="ey-footer">02</p>
    <img src={`${base}ey-mark.svg`} crossOrigin="anonymous" alt="EY" className="ey-logo" />
  </div>;
}