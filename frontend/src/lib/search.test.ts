import { describe, expect, it } from "vitest";
import { fuzzyMatch } from "./search";

describe("filename and folder fuzzy search", () => {
  it("matches paths, mixed case, reordered tokens and typos", () => {
    expect(
      fuzzyMatch("KUAKTA clip", "Clip_004.MP4", "D:\\Trips\\Kuakata\\Arrival"),
    ).toBe(true);
    expect(fuzzyMatch("clpi", "Clip_004.MP4")).toBe(true);
    expect(
      fuzzyMatch("arrival trips", "D:/Trips/Kuakata/Arrival/Clip.mp4"),
    ).toBe(true);
    expect(fuzzyMatch("কুয়াকাটা", "D:/কুয়াকাটা/clip.mp4")).toBe(true);
    expect(fuzzyMatch("", "anything")).toBe(true);
  });
  it("requires every token and avoids fuzzy short-token noise", () => {
    expect(fuzzyMatch("kuakata missing", "Kuakata clip.mp4")).toBe(false);
    expect(fuzzyMatch("xyz", "abc.mp4")).toBe(false);
    expect(fuzzyMatch("clip", undefined, "clip.mp4")).toBe(true);
  });
});
