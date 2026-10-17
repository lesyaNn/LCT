'use client';

import Image from 'next/image';
import { useId, useLayoutEffect, useRef } from 'react';
import styles from './license-verification.module.css';

export function LicenseVerificationStamp({ kind, claimAnimation }: { kind: 'confirmed' | 'not-found'; claimAnimation: () => boolean }) {
  const stampRef = useRef<HTMLDivElement>(null);
  const animationRef = useRef<Animation | null>(null);
  const filterId = `license-stamp-ink-${useId().replaceAll(':', '')}`;
  const missing = kind === 'not-found';

  useLayoutEffect(() => {
    const stamp = stampRef.current;
    const image = stamp?.querySelector('img');
    if (!stamp || !image) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');

    const reveal = () => {
      stamp.style.opacity = '1';
      // The parent owns this guard for the lifetime of the open page. A query
      // refresh can temporarily unmount the stamp without replaying its motion.
      if (!claimAnimation() || motion.matches) return;
      animationRef.current = stamp.animate([
        { opacity: 0, transform: 'translateY(-18px) rotate(-3deg) scale(1)', offset: 0 },
        { opacity: 1, transform: 'translateY(0) rotate(.75deg) scale(1)', offset: .58 },
        { opacity: 1, transform: 'translateY(1px) rotate(-.5deg) scale(.95)', offset: .74 },
        { opacity: 1, transform: 'translateY(0) rotate(0deg) scale(1)', offset: 1 },
      ], { duration: 600, iterations: 1, easing: 'cubic-bezier(.22,.61,.36,1)' });
      animationRef.current.onfinish = () => { animationRef.current = null; };
    };
    const stopMotion = () => {
      if (motion.matches) {
        animationRef.current?.cancel();
        animationRef.current = null;
        stamp.style.opacity = '1';
      }
    };

    // Start with the image visible, rather than animate an unloaded image.
    if (image.complete && image.naturalWidth > 0) reveal();
    else image.addEventListener('load', reveal, { once: true });
    motion.addEventListener('change', stopMotion);
    return () => {
      image.removeEventListener('load', reveal);
      motion.removeEventListener('change', stopMotion);
      // Keep the short animation through React Strict Mode's effect replay.
      // It has no fill and leaves no transforms after finishing.
    };
  }, [claimAnimation]);

  return <div className={styles.stampPlacement}>
    {missing ? <svg className={styles.stampFilter} width="0" height="0" aria-hidden="true" focusable="false">
      <defs><filter id={filterId} colorInterpolationFilters="sRGB">
        {/* The supplied red PNG has an opaque grey checkerboard. Keep its RGB
            artwork intact and make only the neutral background transparent. */}
        <feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  1 -1 0 0 0" />
      </filter></defs>
    </svg> : null}
    <div className={styles.confirmationStamp} ref={stampRef}>
      <Image src={missing ? '/brand/license-not-found-stamp.png' : '/brand/license-confirmed-stamp.png'}
        alt={missing ? 'Красная печать «Лицензия не найдена»' : 'Зелёная печать «Лицензия подтверждена»'}
        width={1536} height={1024} unoptimized loading="eager"
        className={`${styles.stampImage} ${missing ? styles.redStampImage : ''}`}
        style={missing ? { filter: `url(#${filterId})` } : undefined} />
    </div>
  </div>;
}
