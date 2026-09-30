import { Skeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div className="space-y-6" aria-busy="true">
      <Skeleton className="h-4 w-48" />
      <div className="flex items-center gap-4">
        <Skeleton className="h-9 w-9 rounded-full" />
        <div className="space-y-2"><Skeleton className="h-7 w-56" /><Skeleton className="h-4 w-40" /></div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Skeleton className="h-36" /><Skeleton className="h-36" /><Skeleton className="h-36" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}
