import { Badge } from "@/components/ui/badge";
import type { Bug } from "@/lib/types";

const VARIANTS: Record<Bug["severity"], string> = {
  low: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  critical: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

export function SeverityBadge({ severity }: { severity: Bug["severity"] }) {
  return <Badge className={VARIANTS[severity]}>{severity.toUpperCase()}</Badge>;
}
