import { useEffect, useRef, useState } from "react";

/**
 * True once the element has scrolled into view, then stays true (a landing
 * page shouldn't re-hide content the visitor already saw while scrolling
 * back up). Falls back to already-visible when IntersectionObserver isn't
 * available, so content is never permanently hidden.
 */
export function useReveal(threshold = 0.2) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(typeof IntersectionObserver === "undefined");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined" || !ref.current) return undefined;
    const node = ref.current;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold]);

  return [ref, visible];
}
