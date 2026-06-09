
import { motion } from 'framer-motion';
import { useState } from 'react';

const base = import.meta.env.BASE_URL;

const dreams = [
    { src: `${base}gallery/dream_007.png`, title: 'The Awakening', scene: 'Scene 7' },
    { src: `${base}gallery/dream_001.png`, title: 'First Light', scene: 'Scene 1' },
    { src: `${base}gallery/dream_009.png`, title: 'The Crossing', scene: 'Scene 9' },
    { src: `${base}gallery/dream_008.png`, title: 'Ascension', scene: 'Scene 8' },
    { src: `${base}gallery/dream_epstein_008.png`, title: 'Shadows & Truth', scene: 'Scene 8' },
    { src: `${base}gallery/dream_epstein_009.png`, title: 'The Reckoning', scene: 'Scene 9' },
    { src: `${base}gallery/dream_dan3_001.png`, title: 'New Dawn', scene: 'Scene 1' },
    { src: `${base}gallery/dream_dan3_003.png`, title: 'The Journey', scene: 'Scene 3' },
    { src: `${base}gallery/dream_script_001.png`, title: 'Prologue', scene: 'Scene 1' },
    { src: `${base}gallery/dream_script4_002.png`, title: 'Metamorphosis', scene: 'Scene 2' },
    { src: `${base}gallery/dream_latest_001.png`, title: 'Genesis', scene: 'Scene 1' },
    { src: `${base}gallery/dream_latest_002.png`, title: 'Into the Void', scene: 'Scene 2' },
];

const Gallery = () => {
    const [selected, setSelected] = useState<number | null>(null);

    return (
        <section className="gallery-section py-32 relative z-10">
            <div className="container mx-auto px-6">
                <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    className="text-center mb-20"
                >
                    <h2 className="text-sm uppercase tracking-widest text-[var(--color-gold)] mb-4">
                        The Gallery
                    </h2>
                    <h1 className="text-5xl lg:text-6xl font-serif mb-6">
                        Dreams Made Real
                    </h1>
                    <p className="max-w-xl mx-auto opacity-60 text-lg font-light">
                        Every image below was generated entirely by the Psimplicity pipeline —
                        from script to finished art, untouched by human hands.
                    </p>
                </motion.div>

                {/* Masonry Grid */}
                <div className="gallery-grid">
                    {dreams.map((dream, i) => (
                        <motion.div
                            key={i}
                            className="gallery-card"
                            initial={{ y: 40, opacity: 0 }}
                            whileInView={{ y: 0, opacity: 1 }}
                            transition={{ delay: i * 0.08, duration: 0.6 }}
                            viewport={{ once: true, margin: '-50px' }}
                            onClick={() => setSelected(i)}
                        >
                            <div className="gallery-card-inner">
                                <img
                                    src={dream.src}
                                    alt={dream.title}
                                    loading="lazy"
                                />
                                <div className="gallery-card-overlay">
                                    <span className="gallery-card-scene">{dream.scene}</span>
                                    <span className="gallery-card-title">{dream.title}</span>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            </div>

            {/* Lightbox */}
            {selected !== null && (
                <motion.div
                    className="lightbox"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={() => setSelected(null)}
                >
                    <motion.img
                        src={dreams[selected].src}
                        alt={dreams[selected].title}
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ type: 'spring', damping: 25 }}
                        className="lightbox-img"
                    />
                    <div className="lightbox-caption">
                        <h3>{dreams[selected].title}</h3>
                        <span>{dreams[selected].scene}</span>
                    </div>
                </motion.div>
            )}
        </section>
    );
};

export default Gallery;
