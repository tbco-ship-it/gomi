// Scroll reveal for below-the-fold sections: children trail the scroll (rise + blur→sharp, staggered), once, skipped under reduced motion.
(function () {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  const targets = document.querySelectorAll('main > section:not(:first-of-type), main > .grid2, main > h2, main > .tbl, main > .prose, main > .sec, main > .sheet:not(:first-of-type), main > .week, main > .legend, main > .card, main > .list');
  const io = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
  }, { rootMargin: '0px 0px -12% 0px', threshold: 0 });
  targets.forEach(t => {
    if (t.getBoundingClientRect().top <= innerHeight) return;
    // Sections with several blocks (heading, card, note) rise one after another; single blocks rise alone.
    const items = t.matches('.sec, .prose') && t.children.length > 1 ? Array.from(t.children) : [t];
    items.forEach((el, i) => { el.classList.add('rv'); if (i) el.style.setProperty('--d', (i * 110) + 'ms'); });
    t.classList.add('reveal'); io.observe(t);
  });
})();
