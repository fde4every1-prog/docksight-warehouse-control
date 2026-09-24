const base = import.meta.env.BASE_URL;
export default function Slide9() {
 return <div className="w-screen h-screen overflow-hidden relative bg-bg font-body text-text">
 <h1 className="ey-title" style={{top:'3vh',fontSize:'2.5vw'}}>A clear architecture behind every decision.</h1>
 <img src={base + 'docksight-architecture-simplified.svg'} crossOrigin="anonymous" alt="DockSight application architecture: data sources, web interface, services, database and clearly labelled proposed integrations" style={{position:'absolute',left:'12.5vw',top:'10vh',width:'75vw',height:'83vh',objectFit:'contain'}} />
 <p className="ey-footer">09</p><img src={base + 'ey-mark.svg'} crossOrigin="anonymous" alt="EY" className="ey-logo" />
 </div>;
}
