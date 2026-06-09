
import { motion } from 'framer-motion';

const CallToAction = () => {
    return (
        <section className="cta-section relative min-h-[80vh] flex items-center justify-center overflow-hidden">
            {/* Animated background elements */}
            <div className="cta-clouds" />
            <div className="cta-particles">
                {[...Array(20)].map((_, i) => (
                    <div
                        key={i}
                        className="cta-particle"
                        style={{
                            left: `${Math.random() * 100}%`,
                            top: `${Math.random() * 100}%`,
                            animationDelay: `${Math.random() * 6}s`,
                            animationDuration: `${3 + Math.random() * 4}s`,
                        }}
                    />
                ))}
            </div>

            <div className="relative z-20 text-center px-6">
                <motion.div
                    initial={{ opacity: 0, y: 40 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    transition={{ duration: 1 }}
                    viewport={{ once: true }}
                >
                    <h2 className="text-sm uppercase tracking-widest text-[var(--color-gold)] mb-6">
                        Begin Your Story
                    </h2>
                    <h1 className="text-6xl lg:text-8xl font-serif mb-8 leading-tight">
                        Enter the<br />
                        <span className="italic text-[var(--color-gold)]">Machine</span>
                    </h1>
                    <p className="max-w-lg mx-auto text-lg opacity-70 mb-12 font-light leading-relaxed">
                        Paste your script. Choose your style. Watch the engine transmute
                        your words into a fully illustrated picture book — in minutes.
                    </p>

                    <div className="flex flex-col sm:flex-row gap-4 items-center justify-center">
                        <a
                            href="http://localhost:8511"
                            target="_blank"
                            rel="noopener"
                            className="btn-gold"
                        >
                            Launch Psimplicity
                        </a>
                        <a
                            href="https://psio.io"
                            className="cta-link"
                        >
                            ← Back to Psio.io
                        </a>
                    </div>
                </motion.div>
            </div>

            {/* Bottom gradient */}
            <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[var(--color-moss)] to-transparent z-10 pointer-events-none" />

            {/* Footer */}
            <footer className="absolute bottom-6 left-0 right-0 z-20 text-center">
                <p className="text-xs opacity-30 tracking-widest uppercase">
                    Psimplicity — A Psio.io Product &middot; 2026
                </p>
            </footer>
        </section>
    );
};

export default CallToAction;
