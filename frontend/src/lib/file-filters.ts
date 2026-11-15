import { fuzzyMatch } from "./search";

export type FilterFile = {
  path?: string;
  title?: string;
  playlist?: string;
  sha256?: string;
  size: number;
  state?: string;
  control_requested?: string;
};
export type FileFilters = {
  query: string;
  folders: string[];
  types: string[];
  sizes: string[];
  states: string[];
};
export const emptyFilters = (): FileFilters => ({
  query: "",
  folders: [],
  types: [],
  sizes: [],
  states: [],
});
export const folderOf = (file: FilterFile) => {
  const path = file.path?.replaceAll("\\", "/") || "";
  return path.includes("/")
    ? path.slice(0, path.lastIndexOf("/")) || "/"
    : file.playlist || "Unknown folder";
};
export const typeOf = (file: FilterFile) =>
  (file.path || file.title || "")
    .split(/[\\/]/)
    .pop()
    ?.match(/\.([^.]+)$/)?.[1]
    .toUpperCase() || "No extension";
export const stateOf = (file: FilterFile) =>
  file.control_requested || file.state || "COMPLETED";
export const sizeOf = (file: FilterFile) =>
  file.size < 100 * 1024 ** 2
    ? "Under 100 MB"
    : file.size < 1024 ** 3
      ? "100 MB–1 GB"
      : "1 GB or larger";

// OR within each checklist, AND between checklists and free-text search.
export function filterFiles<T extends FilterFile>(
  files: T[],
  filters: FileFilters,
): T[] {
  return files.filter(
    (file) =>
      fuzzyMatch(
        filters.query,
        file.title,
        file.path,
        file.playlist,
        file.sha256,
      ) &&
      (!filters.folders.length || filters.folders.includes(folderOf(file))) &&
      (!filters.types.length || filters.types.includes(typeOf(file))) &&
      (!filters.sizes.length || filters.sizes.includes(sizeOf(file))) &&
      (!filters.states.length || filters.states.includes(stateOf(file))),
  );
}
