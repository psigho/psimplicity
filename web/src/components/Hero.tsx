
import { motion, useScroll, useTransform } from 'framer-motion';
import heroImg from '/hero.png?url';
import { useRef } from 'react';

const Hero = () => {
    const sectionRef = useRef<HTMLElement>(null);
    const { scrollYProgress } = useScroll({
        target: sectionRef,
        offset: ['start start', 'end start'],
    });

    const imgScale = useTransform(scrollYProgress, [0, 1], [1, 1.15]);
    const imgY = useTransform(scrollYProgress, [0, 1], [0, 80]);
    const textY = useTransform(scrollYProgress, [0, 1], [0, -60]);
    const textOpacity = useTransform(scrollYProgress, [0, 0.6], [1, 0]);

    return (
        <section ref={sectionRef} className="relative min-h-screen flex flex-col lg:flex-row items-center justify-center overflow-hidden">
            {/* Floating Gold Dust Particles */}
            <div className="gold-dust-field">
                {[...Array(30)].map((_, i) => (
                    <div
                        key={i}
                        className="gold-dust"
                        style={{
                            left: `${Math.random() * 100}%`,
                            top: `${Math.random() * 100}%`,
                            animationDelay: `${Math.random() * 8}s`,
                            animationDuration: `${4 + Math.random() * 6}s`,
                            width: `${2 + Math.random() * 4}px`,
                            height: `${2 + Math.random() * 4}px`,
                        }}
                    />
                ))}
            </div>

            {/* Left: Philosophy (Text) — scrolls up with parallax */}
            <motion.div
                className="w-full lg:w-1/2 h-screen flex flex-col justify-center px-12 lg:px-24 z-20 relative"
                style={{ y: textY, opacity: textOpacity }}
            >
                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 1.2, delay: 0.3 }}
                >
                    <h2 className="text-[var(--color-gold)] tracking-[0.2em] text-sm uppercase mb-6">
                        Psimplicity Engine v2.0
                    </h2>
                    <h1 className="text-6xl lg:text-8xl leading-[0.9] mb-8">
                        Turn <span className="italic text-[var(--color-gold)]">Philosophy</span><br />
                        into Picture Books.
                    </h1>
                    <p className="max-w-md text-lg opacity-80 mb-12 font-light leading-relaxed">
                        A pipeline for high-reasoning script synthesis, automated art direction,
                        and alchemical transformation.
                    </p>
                    <motion.button
                        className="btn-gold"
                        whileHover={{ scale: 1.05, boxShadow: '0 0 40px rgba(212,175,55,0.3)' }}
                        whileTap={{ scale: 0.98 }}
                    >
                        Enter the Machine
                    </motion.button>
                </motion.div>
            </motion.div>

            {/* Right: Picture Book (Visual) — parallax zoom & drift */}
            <div className="w-full lg:w-1/2 h-[50vh] lg:h-screen relative z-10 overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-r from-[var(--color-moss)] to-transparent z-20 lg:w-32" />
                <div className="absolute inset-0 bg-gradient-to-t from-[var(--color-moss)] to-transparent z-20 h-32 bottom-0 lg:hidden" />

                <motion.img
                    src={heroImg}
                    alt="Alchemical Quill"
                    className="w-full h-full object-cover object-center"
                    initial={{ scale: 1.15, opacity: 0 }}
                    animate={{ scale: 1.0, opacity: 1 }}
                    transition={{ duration: 2, ease: 'easeOut' }}
                    style={{ scale: imgScale, y: imgY }}
                />

                {/* Shimmer overlay */}
                <div className="hero-shimmer" />
            </div>

            {/* Background Texture */}
            <div className="absolute inset-0 pointer-events-none opacity-5 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')] mix-blend-overlay z-0" />

            {/* Scroll indicator */}
            <motion.div
                className="scroll-indicator"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 2.5 }}
            >
                <div className="scroll-line" />
                <span>Scroll</span>
            </motion.div>
        </section>
    );
};

export default Hero;
