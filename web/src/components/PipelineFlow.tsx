
import { motion } from 'framer-motion';

const StepCard = ({ idx, title, desc, icon }: { idx: number, title: string, desc: string, icon: string }) => (
    <motion.div
        className="alchemical-fragment relative p-8 w-80 h-96 flex flex-col items-center text-center justify-between overflow-hidden"
        initial={{ y: 50, opacity: 0 }}
        whileInView={{ y: 0, opacity: 1 }}
        transition={{ delay: idx * 0.2 }}
        viewport={{ once: true }}
    >
        <div className="absolute top-0 left-0 text-[10rem] opacity-5 font-serif leading-none -translate-y-12 -translate-x-8">
            {idx}
        </div>
        <div className="text-4xl mb-4">{icon}</div>
        <div>
            <h3 className="text-2xl mb-4 text-[var(--color-gold)]">{title}</h3>
            <p className="text-sm opacity-80 leading-relaxed text-[var(--color-bone)]">{desc}</p>
        </div>
        <div className="w-full h-1 bg-[var(--color-gold)] opacity-20" />
    </motion.div>
);

const PipelineFlow = () => {
    return (
        <section className="py-32 relative z-10 w-full">
            <div className="container mx-auto px-6">
                <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    className="text-center mb-24"
                >
                    <h2 className="text-sm uppercase tracking-widest text-[var(--color-gold)] mb-4">The Process</h2>
                    <h1 className="text-5xl font-serif">Alchemical Transmutation</h1>
                </motion.div>

                <div className="flex flex-col lg:flex-row gap-12 justify-center items-center relative">
                    {/* Connecting Line (Desktop) */}
                    <div className="hidden lg:block absolute top-1/2 left-20 right-20 h-[1px] bg-gradient-to-r from-transparent via-[var(--color-gold)] to-transparent opacity-30 -z-10" />

                    <StepCard
                        idx={1}
                        title="Script Synthesis"
                        desc="Raw text is parsed, analyzed for narrative beats, and decomposed into visualizable scenes by a high-reasoning model."
                        icon="📜"
                    />
                    <StepCard
                        idx={2}
                        title="Art Direction"
                        desc="The AI Director critiques every frame against 8 dimensions of fidelity, rejecting hallucinations before you see them."
                        icon="👁️"
                    />
                    <StepCard
                        idx={3}
                        title="Rendering"
                        desc="Nano Banana Pro paints the final visuals in a consistent, storybook watercolor style."
                        icon="🎨"
                    />
                </div>
            </div>
        </section>
    );
};

export default PipelineFlow;
