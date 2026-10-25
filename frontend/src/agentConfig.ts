export type FieldType = "text" | "textarea" | "number" | "checkbox";

export interface AgentField {
  name: string;
  label: string;
  type: FieldType;
  rows?: number;
  placeholder?: string;
}

export interface AgentConfig {
  slug: string;
  title: string;
  tagline: string;
  purpose: string;
  accent: string;
  features: string[];
  limitations: string[];
  fields: AgentField[];
  sample: Record<string, string | number | boolean>;
  repo: string;
}

export const agent: AgentConfig = {
  "slug": "plotxyz-resource-optimization-agent",
  "title": "Resource Optimization",
  "tagline": "Right-size the workload before it right-sizes your machine.",
  "purpose": "Recommends worker counts, batch sizes, and cache budgets from supplied CPU, RAM, workload type, and latency constraints.",
  "accent": "#2dd4bf",
  "features": [
    "Workload-aware concurrency heuristics",
    "Memory and latency findings",
    "Before/after settings table"
  ],
  "limitations": [
    "Recommendations are heuristics and require load testing.",
    "The agent does not observe live resource usage."
  ],
  "fields": [
    {
      "name": "cpu_cores",
      "label": "CPU cores",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "ram_gb",
      "label": "RAM (GB)",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "workload",
      "label": "Workload (api, batch, ml)",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "current_workers",
      "label": "Current workers",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "target_latency_ms",
      "label": "Target latency (ms)",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "cpu_cores": 8,
    "ram_gb": 16,
    "workload": "api",
    "current_workers": 24,
    "target_latency_ms": 300
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-resource-optimization-agent"
};
