import { twMerge } from "tailwind-merge";

// twMerge risolve i conflitti fra utility Tailwind sulla stessa proprietà
// (es. px-3 + px-4, inline-flex + flex): a parità di classi vince l'ultima,
// così un className passato dal chiamante può davvero sovrascrivere i default
// del componente invece di essere concatenato accanto a essi nell'HTML.
export function cn(...parts: Array<string | false | null | undefined>): string {
  return twMerge(parts.filter(Boolean).join(" "));
}
