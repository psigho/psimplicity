
import { motion } from 'framer-motion';

const quotes = [
    {
        q: "I built Psimplicity because I was tired of the gap between what I could imagine and what I could create. Stories live in the mind as vivid, cinematic experiences — but the tools to bring them to life were always locked behind expensive studios and specialized skills.",
        label: "The Origin",
    },
    {
        q: "Psimplicity doesn't replace human creativity — it amplifies it. You write the words. The engine paints the worlds. Every scene is an act of collaboration between your imagination and an AI that understands visual storytelling.",
        label: "The Philosophy",
    },
    {
        q: "We tested it with real scripts — documentaries, children's stories, investigative journalism. The pipeline handled them all. It doesn't just generate images; it directs them. It critiques its own work against eight dimensions of fidelity before you ever see a single frame.",
        label: "The Proof",
    },
];

const Interview = () => {
    return (
        <section className="interview-section py-32 relative z-10 overflow-hidden">
            {/* Subtle background glow */}
            <div className="interview-glow" />

            <div className="container mx-auto px-6">
                <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    className="text-center mb-20"
                >
                    <h2 className="text-sm uppercase tracking-widest text-[var(--color-gold)] mb-4">
                        The Vision
                    </h2>
                    <h1 className="text-5xl lg:text-6xl font-serif">
                        Why I Built This
                    </h1>
                </motion.div>

                <div className="interview-grid">
                    {quotes.map((item, i) => (
                        <motion.blockquote
                            key={i}
                            className="interview-quote"
                            initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
                            whileInView={{ opacity: 1, x: 0 }}
                            transition={{ delay: i * 0.15, duration: 0.7 }}
                            viewport={{ once: true }}
                        >
                            <div className="interview-quote-label">{item.label}</div>
                            <p>"{item.q}"</p>
                            <footer className="interview-quote-footer">
                                <div className="interview-divider" />
                                <span>— The Architect</span>
                            </footer>
                        </motion.blockquote>
                    ))}
                </div>

                {/* Tagline */}
                <motion.div
                    className="text-center mt-24"
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5 }}
                >
                    <p className="text-3xl lg:text-4xl font-serif italic text-[var(--color-gold)] opacity-80">
                        "Give your dreams a chance."
                    </p>
                </motion.div>
            </div>
        </section>
    );
};

export default Interview;
