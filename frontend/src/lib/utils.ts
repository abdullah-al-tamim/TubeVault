import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export function bytes(n: number) {
  if (!n) return "0 B";
  const i = Math.min(4, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${["B", "KB", "MB", "GB", "TB"][i]}`;
}
export function percent(done: number, total: number) {
  return total ? Math.min(100, Math.round((done / total) * 100)) : 0;
}
