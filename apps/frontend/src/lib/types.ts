export interface User {
  id: number;
  github_login: string;
  email: string | null;
  avatar_url: string | null;
}

export interface Repository {
  id: number;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export type ReviewStatus = "pending" | "running" | "completed" | "failed";

export interface Bug {
  file: string;
  severity: "low" | "medium" | "high" | "critical";
  description: string;
  suggestion: string;
}

export interface ReviewResult {
  summary: string;
  bugs: Bug[];
}

export interface Review {
  id: number;
  status: ReviewStatus;
  summary: string | null;
  raw_result: ReviewResult | null;
  created_at: string;
  updated_at: string;
}

export interface PullRequest {
  id: number;
  number: number;
  title: string;
  html_url: string;
  state: string;
  created_at: string;
  updated_at: string;
  latest_review: Review | null;
}

export interface PullRequestDetail extends PullRequest {
  repository_id: number;
  repository_full_name: string;
}
