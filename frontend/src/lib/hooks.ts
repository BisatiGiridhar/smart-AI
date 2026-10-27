import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { DatasetVersion, Task } from "./types";

export function useTask(taskId: string | null | undefined) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api<Task>(`/api/tasks/${taskId}`),
    enabled: !!taskId,
    refetchInterval: (q) => (q.state.data && ["succeeded", "failed"].includes(q.state.data.status) ? false : 1500),
  });
}

export function useDatasets() {
  return useQuery({ queryKey: ["datasets"], queryFn: () => api<{ versions: DatasetVersion[]; synthetic_label: string; default_repo: string }>("/api/datasets") });
}

export function useCorpora() {
  const ds = useDatasets();
  const options = [
    { value: "genuine", label: "Genuine candidate workspace" },
    ...(ds.data?.versions ?? []).filter((v) => v.status === "imported").map((v) => ({ value: `dataset:${v.id}`, label: `${v.name} (synthetic)` })),
  ];
  return { options, loading: ds.isLoading, syntheticLabel: ds.data?.synthetic_label };
}
