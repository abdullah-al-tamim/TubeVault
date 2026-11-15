const normalize = (text: string) => text.normalize("NFKC").toLocaleLowerCase();

function distance(a: string, b: string): number {
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  let beforePrevious = previous;
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) {
      row[j] = Math.min(
        row[j - 1] + 1,
        previous[j] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1])
        row[j] = Math.min(row[j], beforePrevious[j - 2] + 1);
    }
    beforePrevious = previous;
    previous = row;
  }
  return previous[b.length];
}

// Every query token must match. Short tokens stay exact to avoid noisy results.
export function fuzzyMatch(
  query: string,
  ...fields: (string | undefined)[]
): boolean {
  const text = normalize(fields.filter(Boolean).join(" "));
  const words = text.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  return normalize(query)
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .every((token) => {
      if (text.includes(token)) return true;
      if (token.length < 4) return false;
      const tolerance = token.length >= 7 ? 2 : 1;
      return words.some(
        (word) =>
          Math.abs(word.length - token.length) <= tolerance &&
          distance(token, word) <= tolerance,
      );
    });
}
