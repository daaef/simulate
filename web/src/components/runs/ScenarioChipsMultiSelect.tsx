"use client";

import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  addScenarioSelection,
  getScenarioSuggestions,
  normalizeScenarioSelection,
  removeScenarioSelection,
} from "../../lib/scenario-chip-utils";

interface ScenarioChipsMultiSelectProps {
  options: string[];
  value: string[];
  disabled?: boolean;
  placeholder?: string;
  onChange: (next: string[]) => void;
  onTouch?: () => void;
  onFocus?: () => void;
  onBlur?: () => void;
}

function arraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  for (let index = 0; index < a.length; index += 1) {
    if (a[index] !== b[index]) return false;
  }
  return true;
}

export default function ScenarioChipsMultiSelect({
  options,
  value,
  disabled = false,
  placeholder = "Type to search scenarios...",
  onChange,
  onTouch,
  onFocus,
  onBlur,
}: ScenarioChipsMultiSelectProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const listboxId = useId();

  const selected = useMemo(() => normalizeScenarioSelection(value || [], options), [value, options]);
  const suggestions = useMemo(
    () => getScenarioSuggestions(options, selected, query),
    [options, selected, query],
  );

  useEffect(() => {
    if (!arraysEqual(selected, value || [])) {
      onChange(selected);
    }
  }, [onChange, selected, value]);

  useEffect(() => {
    if (disabled) {
      setIsOpen(false);
      setQuery("");
      setActiveIndex(0);
    }
  }, [disabled]);

  useEffect(() => {
    setActiveIndex((prev) => {
      if (!suggestions.length) return 0;
      return Math.min(prev, suggestions.length - 1);
    });
  }, [suggestions.length]);

  useEffect(() => {
    const onDocumentMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (!rootRef.current?.contains(target)) {
        setIsOpen(false);
        setActiveIndex(0);
      }
    };
    document.addEventListener("mousedown", onDocumentMouseDown);
    return () => document.removeEventListener("mousedown", onDocumentMouseDown);
  }, []);

  function commit(next: string[]): void {
    onTouch?.();
    onChange(next);
  }

  function addScenario(candidate: string): void {
    const next = addScenarioSelection(selected, candidate, options);
    if (arraysEqual(next, selected)) return;
    commit(next);
    setQuery("");
    setIsOpen(true);
    setActiveIndex(0);
    inputRef.current?.focus();
  }

  function removeScenario(candidate: string): void {
    const next = removeScenarioSelection(selected, candidate);
    if (arraysEqual(next, selected)) return;
    commit(next);
    setIsOpen(true);
    inputRef.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (disabled) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setIsOpen(true);
      setActiveIndex((prev) => (suggestions.length ? (prev + 1) % suggestions.length : 0));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setIsOpen(true);
      setActiveIndex((prev) => (suggestions.length ? (prev - 1 + suggestions.length) % suggestions.length : 0));
      return;
    }
    if (event.key === "Enter") {
      if (!isOpen) {
        setIsOpen(true);
        return;
      }
      if (!suggestions.length) return;
      event.preventDefault();
      addScenario(suggestions[activeIndex] ?? suggestions[0]);
      return;
    }
    if (event.key === "Escape") {
      setIsOpen(false);
      setActiveIndex(0);
      return;
    }
    if (event.key === "Backspace" && !query && selected.length) {
      event.preventDefault();
      removeScenario(selected[selected.length - 1]);
    }
  }

  const activeOptionId =
    isOpen && suggestions.length
      ? `${listboxId}-option-${Math.min(activeIndex, suggestions.length - 1)}`
      : undefined;

  return (
    <div ref={rootRef} className={disabled ? "scenario-chip-combobox is-disabled" : "scenario-chip-combobox"}>
      <div className="scenario-chip-input" onClick={() => inputRef.current?.focus()}>
        {selected.map((scenario) => (
          <span key={scenario} className="scenario-chip-token">
            <span>{scenario}</span>
            <button
              type="button"
              className="scenario-chip-remove"
              onClick={(event) => {
                event.stopPropagation();
                removeScenario(scenario);
              }}
              disabled={disabled}
              aria-label={`Remove ${scenario}`}
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={query}
          role="combobox"
          aria-expanded={isOpen}
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-activedescendant={activeOptionId}
          className="scenario-chip-input-field"
          disabled={disabled}
          placeholder={disabled ? "Available in trace mode only" : placeholder}
          autoComplete="off"
          onFocus={() => {
            onFocus?.();
            if (!disabled) setIsOpen(true);
          }}
          onBlur={() => {
            onBlur?.();
          }}
          onChange={(event) => {
            if (disabled) return;
            setQuery(event.target.value);
            setIsOpen(true);
            setActiveIndex(0);
          }}
          onKeyDown={handleKeyDown}
        />
      </div>
      {isOpen ? (
        <ul className="scenario-chip-dropdown" role="listbox" id={listboxId}>
          {suggestions.length ? (
            suggestions.map((scenario, index) => (
              <li
                key={scenario}
                id={`${listboxId}-option-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                className={index === activeIndex ? "scenario-chip-option active" : "scenario-chip-option"}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseDown={(event) => {
                  event.preventDefault();
                  addScenario(scenario);
                }}
              >
                {scenario}
              </li>
            ))
          ) : (
            <li className="scenario-chip-empty" aria-disabled="true">
              No matching scenarios
            </li>
          )}
        </ul>
      ) : null}
    </div>
  );
}
