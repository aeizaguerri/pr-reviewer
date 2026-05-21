export type HealthResponse = {
  status: string;
  neo4j: boolean;
};

export type ProviderInfo = {
  key: string;
  description: string;
  default_model: string;
  key_label: string;
  supports_structured_output: boolean;
};

export type ProvidersResponse = {
  providers: ProviderInfo[];
};

export type ReviewRequest = {
  owner: string;
  repo: string;
  pr_number: number;
  provider: string;
  model: string;
  base_url_override: string;
};

export type BugReport = {
  file: string;
  line: number;
  severity: string;
  description: string;
  suggestion: string;
  category: string;
  source: string;
};

export type ImpactWarning = {
  severity: string;
  description: string;
  changed_file: string;
  changed_entity: string;
  affected_service: string;
  affected_repository: string;
  relationship_type: string;
};

export type ReviewHealth = {
  status: string;
  warnings: string[];
};

export type ReviewResponse = {
  summary: string;
  approved: boolean;
  bugs: BugReport[];
  impact_warnings: ImpactWarning[];
  review_health?: ReviewHealth | null;
};
