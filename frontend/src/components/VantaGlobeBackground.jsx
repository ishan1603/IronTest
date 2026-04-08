import React, { useEffect, useRef } from "react";

const THREE_CDN =
  "https://cdnjs.cloudflare.com/ajax/libs/three.js/r134/three.min.js";
const VANTA_CDN =
  "https://cdn.jsdelivr.net/npm/vanta@latest/dist/vanta.globe.min.js";

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === "true") {
        resolve();
        return;
      }
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error(`Failed to load script: ${src}`)),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => {
      script.dataset.loaded = "true";
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

export default function VantaGlobeBackground({ theme = "dark" }) {
  const vantaRef = useRef(null);
  const vantaEffectRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const setupVanta = async () => {
      try {
        await loadScript(THREE_CDN);
        await loadScript(VANTA_CDN);

        if (cancelled || !vantaRef.current || !window.VANTA?.GLOBE) {
          return;
        }

        if (vantaEffectRef.current) {
          vantaEffectRef.current.destroy();
          vantaEffectRef.current = null;
        }

        const isLight = theme !== "dark";

        vantaEffectRef.current = window.VANTA.GLOBE({
          el: vantaRef.current,
          mouseControls: true,
          touchControls: true,
          gyroControls: false,
          minHeight: 200,
          minWidth: 200,
          scale: 1,
          scaleMobile: 1,
          color: isLight ? 0x1d101 : 0x7de504,
          color2: isLight ? 0x0 : 0x0,
          backgroundColor: isLight ? 0xe0dada : 0x0,
        });
      } catch (error) {
        console.error("[Vanta] Failed to initialize globe", error);
      }
    };

    setupVanta();

    return () => {
      cancelled = true;
      if (vantaEffectRef.current) {
        vantaEffectRef.current.destroy();
        vantaEffectRef.current = null;
      }
    };
  }, [theme]);

  return <div ref={vantaRef} className="absolute inset-0" aria-hidden="true" />;
}
