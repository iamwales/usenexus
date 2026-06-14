"use client";

import { useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import { sectionDots } from "@/components/site/data";

export function SiteMotion() {
  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
    gsap.defaults({ ease: "power2.out", duration: 0.65 });

    const mm = gsap.matchMedia();
    const triggers: ScrollTrigger[] = [];
    const cleanups: Array<() => void> = [];
    const announce = document.querySelector<HTMLElement>(".announce");

    if (announce) {
      const syncAnnounceHeight = () => {
        const height = Math.ceil(announce.getBoundingClientRect().height);
        document.documentElement.style.setProperty("--announce-height", `${height}px`);
      };
      const observer = new ResizeObserver(syncAnnounceHeight);

      syncAnnounceHeight();
      observer.observe(announce);
      window.addEventListener("resize", syncAnnounceHeight);

      cleanups.push(() => {
        observer.disconnect();
        window.removeEventListener("resize", syncAnnounceHeight);
      });
    }

    mm.add(
      {
        isDesktop: "(min-width: 769px)",
        reduceMotion: "(prefers-reduced-motion: reduce)"
      },
      (ctx) => {
        const { isDesktop, reduceMotion } = ctx.conditions as {
          isDesktop: boolean;
          reduceMotion: boolean;
        };

        if (reduceMotion) {
          gsap.set(".reveal", { y: 0 });
          return;
        }

        const heroReveal = document.querySelectorAll("#hero .reveal");
        gsap.fromTo(
          heroReveal,
          { y: isDesktop ? 22 : 14 },
          { y: 0, stagger: 0.1, delay: 0.15 }
        );

        document.querySelectorAll(".reveal:not(#hero .reveal)").forEach((el) => {
          gsap.fromTo(
            el,
            { y: isDesktop ? 18 : 12 },
            {
              y: 0,
              scrollTrigger: {
                trigger: el,
                start: "top 90%",
                toggleActions: "play none none none"
              }
            }
          );
        });

        document.querySelectorAll(".conn-card").forEach((card, i) => {
          triggers.push(
            ScrollTrigger.create({
              trigger: card,
              start: "top 92%",
              onEnter: () =>
                gsap.fromTo(
                  card,
                  { y: 12, scale: 0.98 },
                  { y: 0, scale: 1, duration: 0.4, delay: (i % 4) * 0.06 }
                )
            })
          );
        });

        triggers.push(
          ScrollTrigger.create({
            trigger: ".arch-strip",
            start: "top 88%",
            onEnter: () =>
              gsap.fromTo(
                ".arch-node, .arch-arrow",
                { y: 8 },
                { y: 0, stagger: 0.04, duration: 0.35 }
              )
          })
        );

        triggers.push(
          ScrollTrigger.create({
            trigger: ".stats-row",
            start: "top 90%",
            onEnter: () =>
              gsap.fromTo(
                ".stat-cell",
                { y: 14 },
                { y: 0, stagger: 0.08, duration: 0.5 }
              )
          })
        );

        document.querySelectorAll(".blog-card").forEach((card, i) => {
          triggers.push(
            ScrollTrigger.create({
              trigger: card,
              start: "top 92%",
              onEnter: () =>
                gsap.fromTo(
                  card,
                  { y: 16 },
                  { y: 0, duration: 0.45, delay: (i % 3) * 0.08 }
                )
            })
          );
        });

        document.querySelectorAll(".conn-card, .blog-card, .uc-item, .deploy-card").forEach((el) => {
          const enter = () => gsap.to(el, { y: -2, duration: 0.2, ease: "power1.out" });
          const leave = () => gsap.to(el, { y: 0, duration: 0.25 });
          el.addEventListener("mouseenter", enter);
          el.addEventListener("mouseleave", leave);
          cleanups.push(() => {
            el.removeEventListener("mouseenter", enter);
            el.removeEventListener("mouseleave", leave);
          });
        });

        triggers.push(
          ScrollTrigger.create({
            trigger: "#final-cta",
            start: "top 85%",
            onEnter: () =>
              gsap.fromTo(".cta-h", { y: 32 }, { y: 0, duration: 0.8 })
          })
        );
      }
    );

    mm.add("(max-width: 768px)", () => {
      document.querySelectorAll(".reveal").forEach((el) => {
        gsap.fromTo(
          el,
          { y: 12 },
          {
            y: 0,
            duration: 0.5,
            scrollTrigger: {
              trigger: el,
              start: "top 93%",
              toggleActions: "play none none none"
            }
          }
        );
      });
    });

    triggers.push(
      ScrollTrigger.create({
        start: "top -50",
        onEnter: () => {
          const nav = document.getElementById("main-nav");
          if (nav) nav.style.boxShadow = "0 1px 12px rgba(0,0,0,0.06)";
        },
        onLeaveBack: () => {
          const nav = document.getElementById("main-nav");
          if (nav) nav.style.boxShadow = "none";
        }
      })
    );

    const dots = Array.from(document.querySelectorAll(".side-dot"));
    sectionDots.forEach((id, i) => {
      const el = document.getElementById(id);
      if (!el) return;

      triggers.push(
        ScrollTrigger.create({
          trigger: el,
          start: "top center",
          end: "bottom center",
          onEnter: () => {
            dots.forEach((dot) => dot.classList.remove("active"));
            dots[i]?.classList.add("active");
          },
          onEnterBack: () => {
            dots.forEach((dot) => dot.classList.remove("active"));
            dots[i]?.classList.add("active");
          }
        })
      );
    });

    dots.forEach((dot, i) => {
      const click = () => {
        const target = document.getElementById(sectionDots[i]);
        const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        target?.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth" });
      };
      dot.addEventListener("click", click);
      cleanups.push(() => dot.removeEventListener("click", click));
    });

    return () => {
      cleanups.forEach((cleanup) => cleanup());
      triggers.forEach((trigger) => trigger.kill());
      mm.revert();
    };
  }, []);

  return null;
}
