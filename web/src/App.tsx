
import './stitch.css';
import Hero from './components/Hero';
import PipelineFlow from './components/PipelineFlow';
import Gallery from './components/Gallery';
import Interview from './components/Interview';
import CallToAction from './components/CallToAction';

function App() {
    return (
        <div className="min-h-screen w-full overflow-x-hidden selection:bg-[var(--color-gold)] selection:text-[var(--color-moss)]">
            <Hero />
            <PipelineFlow />
            <Gallery />
            <Interview />
            <CallToAction />
        </div>
    );
}

export default App;
