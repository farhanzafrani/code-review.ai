import { Badge } from "@/components/ui/badge";
import type { ReviewStatus } from "@/lib/types";

const VARIANTS: Record<ReviewStatus, { label: string; className: string }> = {
  pending: { label: "Pending", className: "bg-muted text-muted-foreground" },
  running: { label: "Reviewing…", className: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300" },
  completed: { label: "Reviewed", className: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300" },
  failed: { label: "Failed", className: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" },
};

export function StatusBadge({ status }: { status: ReviewStatus | null }) {
  if (!status) {
    return <Badge variant="outline">No review yet</Badge>;
  }
  const { label, className } = VARIANTS[status];
  return <Badge className={className}>{label}</Badge>;
}
