/* Progressive enhancement: the original image links remain usable without JS. */
(() => {
  'use strict';
  document.querySelectorAll('.bt-banner-slider').forEach((track, carouselIndex) => {
    const slides = Array.from(track.children).filter((item) => item.matches('.wp-block-image'));
    if (slides.length < 2 || track.closest('.bt-carousel')) return;

    const region = document.createElement('section');
    region.className = 'bt-carousel';
    region.setAttribute('aria-label', 'Пропозиції BeTrendy');
    region.setAttribute('aria-roledescription', 'карусель');
    track.before(region);
    region.append(track);
    track.id = track.id || `bt-carousel-${carouselIndex + 1}`;
    track.tabIndex = 0;
    track.setAttribute('aria-label', 'Банери. Гортайте або використовуйте стрілки клавіатури.');

    const controls = document.createElement('div');
    controls.className = 'bt-carousel-controls';
    const dotsContainer = document.createElement('div');
    dotsContainer.className = 'bt-carousel-dots';
    dotsContainer.setAttribute('role', 'group');
    dotsContainer.setAttribute('aria-label', 'Обрати банер');
    const count = document.createElement('span');
    count.className = 'bt-carousel-count';
    count.setAttribute('aria-live', 'polite');
    count.setAttribute('aria-atomic', 'true');
    let active = 0;
    let target = 0;
    let scrollTimer;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const makeButton = (label, text, className, handler) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = className;
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-controls', track.id);
      button.textContent = text;
      button.addEventListener('click', handler);
      return button;
    };
    const update = (index) => {
      active = index;
      dots.forEach((dot, i) => dot.setAttribute('aria-current', String(i === index)));
      count.textContent = `${String(index + 1).padStart(2, '0')} / ${String(slides.length).padStart(2, '0')}`;
      count.setAttribute('aria-label', `Банер ${index + 1} з ${slides.length}`);
      slides.forEach((slide, i) => { slide.inert = i !== index; });
    };
    const position = (index) => track.scrollLeft + slides[index].getBoundingClientRect().left - track.getBoundingClientRect().left;
    const go = (index, instant = false) => {
      target = (index + slides.length) % slides.length;
      track.scrollTo({ left: position(target), behavior: instant || reduceMotion.matches ? 'instant' : 'smooth' });
      update(target);
    };
    const dots = slides.map((slide, index) => {
      slide.setAttribute('role', 'group');
      slide.setAttribute('aria-roledescription', 'слайд');
      slide.setAttribute('aria-label', `${index + 1} з ${slides.length}`);
      const title = slide.querySelector('img')?.alt || `Банер ${index + 1}`;
      const dot = makeButton(`Показати: ${title}`, '', 'bt-carousel-dot', () => go(index));
      dotsContainer.append(dot);
      return dot;
    });
    const previous = makeButton('Попередній банер', '←', 'bt-carousel-arrow', () => go(target - 1));
    const next = makeButton('Наступний банер', '→', 'bt-carousel-arrow', () => go(target + 1));
    controls.append(previous, dotsContainer, count, next);
    region.append(controls);
    track.addEventListener('keydown', (event) => {
      const offsets = { ArrowLeft: -1, ArrowRight: 1 };
      if (event.key in offsets) { event.preventDefault(); go(target + offsets[event.key]); }
      if (event.key === 'Home' || event.key === 'End') {
        event.preventDefault(); go(event.key === 'Home' ? 0 : slides.length - 1);
      }
    });
    const settle = () => {
      const left = track.getBoundingClientRect().left;
      const nearest = slides.reduce((best, slide, i) => Math.abs(slide.getBoundingClientRect().left - left) < Math.abs(slides[best].getBoundingClientRect().left - left) ? i : best, 0);
      target = nearest;
      update(nearest);
    };
    track.addEventListener('scroll', () => {
      window.clearTimeout(scrollTimer);
      scrollTimer = window.setTimeout(settle, 140);
    }, { passive: true });
    if ('ResizeObserver' in window) {
      let width = track.clientWidth;
      new ResizeObserver(() => {
        if (track.clientWidth !== width) { width = track.clientWidth; go(active, true); }
      }).observe(track);
    }
    update(0);
  });
})();
