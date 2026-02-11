export interface Project {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  repo_full_name: string;
  repo_url: string;
  default_branch: string;
  created_at: string;
  updated_at: string;
}

export interface Board {
  id: string;
  project_id: string;
  name: string;
  columns: BoardColumn[];
  created_at: string;
}

export interface BoardColumn {
  id: string;
  name: string;
  position: number;
  ticket_status: string;
}

export interface Ticket {
  id: string;
  column_id: string;
  project_id: string;
  created_by_id: string;
  title: string;
  description: string | null;
  position: number;
  status: string;
  agent_type: string | null;
  runtime: string | null;
  priority: string | null;
  complexity: string | null;
  refined_description: string | null;
  acceptance_criteria: string | null;
  context_files: string[] | null;
  triage_reasoning: string | null;
  branch_name: string | null;
  pr_url: string | null;
  pr_number: number | null;
  created_at: string;
  updated_at: string;
}

export interface Execution {
  id: string;
  ticket_id: string;
  agent_type: string;
  runtime: string;
  status: string;
  session_id: string | null;
  total_tokens: number;
  total_cost: number;
  duration_seconds: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  error_message: string | null;
}

export interface ExecutionLog {
  id: string;
  execution_id: string;
  sequence: number;
  log_type: string;
  content: string;
  created_at: string;
}

export interface Notification {
  id: string;
  user_id: string;
  ticket_id: string | null;
  type: string;
  title: string;
  body: string | null;
  read: boolean;
  created_at: string;
}

export interface PlanningMessage {
  id: string;
  ticket_id: string;
  sequence: number;
  role: "user" | "assistant";
  content: string;
  is_streaming: boolean;
  created_at: string;
}

export interface DashboardStats {
  project_count: number;
  open_ticket_count: number;
  pr_count: number;
}
