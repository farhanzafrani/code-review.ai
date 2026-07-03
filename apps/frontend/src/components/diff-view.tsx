import { cn } from "@/lib/utils";

function lineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-muted-foreground";
  if (line.startsWith("+")) return "bg-green-500/10 text-green-700 dark:text-green-400";
  if (line.startsWith("-")) return "bg-red-500/10 text-red-700 dark:text-red-400";
  if (line.startsWith("@@")) return "text-blue-600 dark:text-blue-400";
  return "text-foreground";
}

export function DiffView({ diff }: { diff: string }) {
  const lines = diff.split("\n");
  return (
    <pre className="max-h-[32rem] overflow-auto rounded-md border bg-muted/30 p-3 text-xs leading-5">
      {lines.map((line, i) => (
        <div key={i} className={cn("whitespace-pre", lineClass(line))}>
          {line || " "}
        </div>
      ))}
    </pre>
  );
}
