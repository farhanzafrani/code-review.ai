import { Badge } from "@/components/ui/badge";
import type { QualityGateStatus } from "@/lib/types";

const VARIANTS: Record<QualityGateStatus, { label: string; className: string }> = {
  OK: { label: "✅ Passed", className: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300" },
  ERROR: { label: "❌ Failed", className: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" },
  NONE: { label: "⚪ None", className: "bg-muted text-muted-foreground" },
};

export function QualityGateBadge({ status }: { status: QualityGateStatus }) {
  const { label, className } = VARIANTS[status];
  return <Badge className={className}>{label}</Badge>;
}
