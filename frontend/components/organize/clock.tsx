"use client";

import { useEffect, useState } from "react";

export function Clock() {
  const [time, setTime] = useState<string>("--:--:--");

  useEffect(() => {
    const fmt = () => new Date().toLocaleTimeString("it-IT", { hour12: false });
    const raf = requestAnimationFrame(() => setTime(fmt()));
    const id = setInterval(() => setTime(fmt()), 1000);
    return () => {
      cancelAnimationFrame(raf);
      clearInterval(id);
    };
  }, []);

  return <span className="tnum text-faint">{time}</span>;
}
