import { useId, useState } from "react";
import { Button } from "./ui/button";
import {
  emptyFilters,
  folderOf,
  typeOf,
  sizeOf,
  stateOf,
  type FilterFile,
  type FileFilters,
} from "../lib/file-filters";

export function FileFilterBar({
  files,
  value,
  onChange,
  searchLabel,
  shown,
  disabled = false,
  statuses = false,
}: {
  files: FilterFile[];
  value: FileFilters;
  onChange: (value: FileFilters) => void;
  searchLabel: string;
  shown: number;
  disabled?: boolean;
  statuses?: boolean;
}) {
  const id = useId();
  const [folderSearch, setFolderSearch] = useState("");
  const facets: {
    key: "folders" | "types" | "sizes" | "states";
    label: string;
    get: (file: FilterFile) => string;
  }[] = [
    { key: "folders", label: "Folders", get: folderOf },
    { key: "types", label: "File types", get: typeOf },
    { key: "sizes", label: "File sizes", get: sizeOf },
    ...(statuses
      ? [{ key: "states" as const, label: "Statuses", get: stateOf }]
      : []),
  ];
  const active = !!value.query || facets.some((f) => value[f.key].length > 0);
  return (
    <div className="file-filters">
      <div className="file-filter-heading">
        <label className="file-search" htmlFor={id}>
          {searchLabel}
          <input
            id={id}
            type="search"
            placeholder="Filename, folder or collection — typos welcome"
            value={value.query}
            disabled={disabled}
            onChange={(e) => onChange({ ...value, query: e.target.value })}
          />
        </label>
        <span aria-live="polite">
          {shown} of {files.length} files match
        </span>
        <Button
          variant="outline"
          disabled={disabled || !active}
          onClick={() => {
            onChange(emptyFilters());
            setFolderSearch("");
          }}
        >
          Clear filters
        </Button>
      </div>
      <div className="file-filter-facets">
        {facets.map((facet) => {
          const options = [
            ...new Set([...files.map(facet.get), ...value[facet.key]]),
          ].sort((a, b) => a.localeCompare(b));
          const counts = new Map<string, number>();
          files.forEach((file) => {
            const key = facet.get(file);
            counts.set(key, (counts.get(key) || 0) + 1);
          });
          return (
            <details className="file-filter-facet" key={facet.key}>
              <summary>
                {facet.label}
                {value[facet.key].length
                  ? ` (${value[facet.key].length})`
                  : " · All"}
              </summary>
              <fieldset disabled={disabled}>
                <legend className="sr-only">{facet.label}</legend>
                {facet.key === "folders" && (
                  <input
                    type="search"
                    aria-label="Find a folder filter"
                    placeholder="Find folder…"
                    value={folderSearch}
                    onChange={(e) => setFolderSearch(e.target.value)}
                  />
                )}
                <div className="file-filter-options">
                  {options
                    .filter(
                      (option) =>
                        facet.key !== "folders" ||
                        option
                          .toLocaleLowerCase()
                          .includes(folderSearch.toLocaleLowerCase()),
                    )
                    .map((option) => (
                      <label key={option} title={option}>
                        <input
                          type="checkbox"
                          checked={value[facet.key].includes(option)}
                          onChange={(e) =>
                            onChange({
                              ...value,
                              [facet.key]: e.target.checked
                                ? [...value[facet.key], option]
                                : value[facet.key].filter((v) => v !== option),
                            })
                          }
                        />
                        <span>{option}</span>
                        <small>{counts.get(option) || 0}</small>
                      </label>
                    ))}
                </div>
                {!options.length && <p>No options yet.</p>}
              </fieldset>
            </details>
          );
        })}
      </div>
      <small>
        Filters update as you type or check options. Multiple choices in one
        checklist match any selected option.
      </small>
    </div>
  );
}
