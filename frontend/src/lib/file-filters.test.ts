import { describe, expect, it } from "vitest";
import { emptyFilters, filterFiles, folderOf, typeOf } from "./file-filters";

const files = [
  {
    id: "a",
    title: "Arrival",
    path: "C:\\Trips\\Kuakata\\clip.MP4",
    size: 50 * 1024 ** 2,
    state: "QUEUED",
  },
  {
    id: "b",
    title: "Sunset",
    path: "C:/Trips/Kuakata/sunset.mov",
    size: 1024 ** 3,
    state: "PAUSED",
  },
  {
    id: "c",
    title: "City",
    path: "C:/Trips/Dhaka/city.mp4",
    size: 100 * 1024 ** 2,
    state: "QUEUED",
    control_requested: "REMOVED",
  },
];
describe("file checklist filters", () => {
  it("matches any choice within a facet and combines independent facets", () => {
    const filters = {
      ...emptyFilters(),
      folders: ["C:/Trips/Kuakata"],
      types: ["MP4", "MOV"],
      query: "kuakta",
    };
    expect(filterFiles(files, filters).map((f) => f.id)).toEqual(["a", "b"]);
    expect(
      filterFiles(files, { ...filters, sizes: ["1 GB or larger"] }).map(
        (f) => f.id,
      ),
    ).toEqual(["b"]);
    expect(
      filterFiles(files, { ...filters, states: ["QUEUED"] }).map((f) => f.id),
    ).toEqual(["a"]);
  });
  it("handles size boundaries, requested holds and clearing filters", () => {
    expect(
      filterFiles(files, { ...emptyFilters(), sizes: ["100 MB–1 GB"] }).map(
        (f) => f.id,
      ),
    ).toEqual(["c"]);
    expect(
      filterFiles(files, { ...emptyFilters(), states: ["REMOVED"] }).map(
        (f) => f.id,
      ),
    ).toEqual(["c"]);
    expect(filterFiles(files, emptyFilters())).toEqual(files);
    expect(
      filterFiles(files, { ...emptyFilters(), folders: ["missing"] }),
    ).toEqual([]);
  });
  it("normalizes folder separators and extensions without confusing filenames for folders", () => {
    expect(folderOf(files[0])).toBe("C:/Trips/Kuakata");
    expect(folderOf({ path: "clip.mp4", playlist: "Camera", size: 0 })).toBe(
      "Camera",
    );
    expect(typeOf(files[0])).toBe("MP4");
    expect(typeOf({ title: "clip", size: 0 })).toBe("No extension");
  });
});
