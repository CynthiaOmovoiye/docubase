export function formatJoined(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function axiosDetail(err: unknown): string {
  const ax = err as { response?: { data?: { detail?: unknown } } };
  const d = ax.response?.data?.detail;
  if (typeof d === "string") return d;
  if (err instanceof Error) return err.message;
  return "Request failed";
}
