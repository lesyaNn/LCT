'use client';

import { useEffect, useState } from 'react';

/**
 * Debounce a value so a burst of edits (typing a date, ticking checkboxes)
 * results in one request instead of one per keystroke. The previous value is
 * kept until the new one settles, which is what lets the panels keep showing
 * the last good selection while the next one loads.
 */
export function useDebouncedValue<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    if (value === debounced) return;
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, debounced, delayMs]);

  return debounced;
}
